"""
OSM Loader — instant prebaked spawn + progressive live expand (<100m).
Buildings = obstacles. Roads via public OSRM (not local graph).
"""

from typing import Tuple, List, Dict, Optional
import time
import pickle
import math
from pathlib import Path

try:
    import osmnx as ox
    from shapely.geometry import Point
    HAS_OSMNX = True
    ox.settings.timeout = 12
    ox.settings.overpass_rate_limit = True
except ImportError:
    HAS_OSMNX = False
    ox = None
    try:
        from shapely.geometry import Point
    except ImportError:
        Point = None  # type: ignore

_cache: Dict[Tuple, dict] = {}
_cache_timestamps: Dict[Tuple, float] = {}
CACHE_TTL = 1200

DISK_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".osm_cache"
DISK_CACHE_TTL = 3600 * 24

INITIAL_RADIUS_M = 100
EXPAND_RADIUS_M = 90  # <100m tiles
EXPAND_TRIGGER_M = 55


def _cache_key(lat: float, lon: float, dist: int) -> Tuple:
    return (round(lat, 4), round(lon, 4), dist)


def _disk_path(key: Tuple) -> Path:
    DISK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return DISK_CACHE_DIR / f"osm_{key[0]}_{key[1]}_{key[2]}.pkl"


def _load_disk(key: Tuple) -> Optional[dict]:
    path = _disk_path(key)
    if not path.exists():
        return None
    try:
        if time.time() - path.stat().st_mtime > DISK_CACHE_TTL:
            return None
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _save_disk(key: Tuple, data: dict):
    try:
        to_save = {
            "buildings": data.get("buildings", []),
            "building_coords": data.get("building_coords", []),
            "road_lines": data.get("road_lines", []),
            "road_graph": None,
            "success": data.get("success", False),
            "error": data.get("error"),
            "center": data.get("center"),
            "radius": data.get("radius"),
        }
        with open(_disk_path(key), "wb") as f:
            pickle.dump(to_save, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass


def _empty_result(lat: float, lon: float, radius: int) -> dict:
    return {
        "buildings": [],
        "building_coords": [],
        "road_graph": None,
        "road_lines": [],
        "success": False,
        "error": None,
        "from_cache": False,
        "center": (lat, lon),
        "radius": radius,
        "source": "empty",
    }


def load_buildings_and_roads(
    lat: float,
    lon: float,
    dist: int = INITIAL_RADIUS_M,
    use_cache: bool = True,
    load_roads: bool = False,
) -> dict:
    """Live Overpass fetch (buildings only). May be slow — use only for expand."""
    result = _empty_result(lat, lon, dist)
    if not HAS_OSMNX:
        result["error"] = "OSMnx not installed"
        return result

    key = _cache_key(lat, lon, dist)
    now = time.time()
    if use_cache and key in _cache and now - _cache_timestamps.get(key, 0) < CACHE_TTL:
        cached = dict(_cache[key])
        cached["from_cache"] = True
        return cached
    if use_cache:
        disk = _load_disk(key)
        if disk is not None:
            _cache[key] = disk
            _cache_timestamps[key] = now
            out = dict(disk)
            out["from_cache"] = True
            return out

    try:
        bldg_gdf = ox.features_from_point((lat, lon), tags={"building": True}, dist=dist)
        buildings, building_coords = [], []
        if bldg_gdf is not None and not bldg_gdf.empty:
            for geom in bldg_gdf.geometry:
                if geom is None:
                    continue
                if geom.geom_type == "Polygon":
                    buildings.append(geom)
                    building_coords.append([(p[1], p[0]) for p in geom.exterior.coords])
                elif geom.geom_type == "MultiPolygon":
                    for poly in geom.geoms:
                        buildings.append(poly)
                        building_coords.append([(p[1], p[0]) for p in poly.exterior.coords])
        result["buildings"] = buildings
        result["building_coords"] = building_coords
        result["success"] = True
        result["center"] = (lat, lon)
        result["radius"] = dist
        result["source"] = "live"
        _cache[key] = result
        _cache_timestamps[key] = now
        _save_disk(key, result)
        return result
    except Exception as e:
        result["error"] = str(e)[:120]
        return result


def merge_map_data(base: dict, extra: dict) -> dict:
    if not extra or not extra.get("success"):
        return base or _empty_result(0, 0, 0)
    out = dict(base) if base else _empty_result(0, 0, 0)
    out["buildings"] = list(out.get("buildings") or []) + list(extra.get("buildings") or [])
    out["building_coords"] = list(out.get("building_coords") or []) + list(
        extra.get("building_coords") or []
    )
    out["road_lines"] = list(out.get("road_lines") or []) + list(extra.get("road_lines") or [])
    out["success"] = True
    old_r = out.get("radius") or 0
    new_r = extra.get("radius") or 0
    # covered radius grows with robot as center of scan
    out["radius"] = max(old_r, new_r)
    out["center"] = extra.get("center") or out.get("center")
    out["source"] = "merged"
    return out


def needs_expansion(map_data: dict, lat: float, lon: float) -> bool:
    if not map_data or not map_data.get("success"):
        return True
    center = map_data.get("center")
    radius = map_data.get("radius") or INITIAL_RADIUS_M
    if not center:
        return True
    clat, clon = center
    dlat = (lat - clat) * 111320.0
    dlon = (lon - clon) * 111320.0 * max(0.2, abs(math.cos(math.radians(lat))))
    dist = (dlat ** 2 + dlon ** 2) ** 0.5
    return dist > max(20.0, radius - EXPAND_TRIGGER_M)


def expand_around(map_data: dict, lat: float, lon: float, dist: int = EXPAND_RADIUS_M) -> dict:
    """Scan-style: robot is center of a new <100m tile; merge into known map."""
    dist = min(dist, 99)  # hard cap <100m
    extra = load_buildings_and_roads(lat, lon, dist=dist, use_cache=True, load_roads=False)
    if not extra.get("success"):
        # keep prebaked; do not fail the session
        return map_data
    merged = merge_map_data(map_data, extra)
    # recent scan center follows the robot
    merged["center"] = (lat, lon)
    merged["radius"] = max(map_data.get("radius") or 0, dist)
    return merged


def point_in_buildings(lat: float, lon: float, buildings: list) -> bool:
    if not buildings or Point is None:
        return False
    pt = Point(lon, lat)
    for poly in buildings:
        try:
            if poly.contains(pt) or poly.intersects(pt.buffer(0.000015)):
                return True
        except Exception:
            continue
    return False


def find_free_spawn(lat: float, lon: float, buildings: list, max_radius_m: float = 80.0) -> Tuple[float, float]:
    if not point_in_buildings(lat, lon, buildings):
        return lat, lon
    for radius in [8, 15, 25, 35, 50, 65, 80]:
        if radius > max_radius_m:
            break
        for angle_deg in range(0, 360, 25):
            rad = math.radians(angle_deg)
            d_north = radius * math.cos(rad)
            d_east = radius * math.sin(rad)
            nlat = lat + d_north / 111320.0
            nlon = lon + d_east / (111320.0 * math.cos(math.radians(lat)) + 1e-8)
            if not point_in_buildings(nlat, nlon, buildings):
                return nlat, nlon
    return lat, lon


def get_nearest_road_node(G, lat: float, lon: float):
    if G is None or not HAS_OSMNX:
        return None
    try:
        return ox.distance.nearest_nodes(G, lon, lat)
    except Exception:
        return None
