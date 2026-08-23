"""
OSM Loader — progressive, fast, on-demand.
Load only a small area around the robot first (~100m),
then expand outward as the robot moves.
Buildings = obstacles, roads = preferred paths.
"""

from typing import Tuple, List, Dict, Optional, Any
import time
import pickle
from pathlib import Path

try:
    import osmnx as ox
    from shapely.geometry import Point
    from shapely.ops import unary_union
    HAS_OSMNX = True
    ox.settings.timeout = 25  # fail faster
    ox.settings.overpass_rate_limit = True
except ImportError:
    HAS_OSMNX = False
    ox = None

# In-memory cache
_cache: Dict[Tuple, dict] = {}
_cache_timestamps: Dict[Tuple, float] = {}
CACHE_TTL = 900

DISK_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".osm_cache"
DISK_CACHE_TTL = 3600 * 12

# Progressive loading defaults
INITIAL_RADIUS_M = 100   # ~100x100 m around spawn (fast)
EXPAND_RADIUS_M = 80     # each expansion tile
EXPAND_TRIGGER_M = 40    # expand when robot is this close to edge of covered area


def _cache_key(lat: float, lon: float, dist: int) -> Tuple:
    return (round(lat, 4), round(lon, 4), dist)


def _disk_path(key: Tuple) -> Path:
    DISK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    name = f"osm_{key[0]}_{key[1]}_{key[2]}.pkl"
    return DISK_CACHE_DIR / name


def _load_disk(key: Tuple) -> Optional[dict]:
    path = _disk_path(key)
    if not path.exists():
        return None
    try:
        age = time.time() - path.stat().st_mtime
        if age > DISK_CACHE_TTL:
            return None
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _save_disk(key: Tuple, data: dict):
    try:
        # Avoid pickling huge graphs if possible — keep what we have
        to_save = {
            "buildings": data.get("buildings", []),
            "building_coords": data.get("building_coords", []),
            "road_lines": data.get("road_lines", []),
            "road_graph": data.get("road_graph"),
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
    }


def load_buildings_and_roads(
    lat: float,
    lon: float,
    dist: int = INITIAL_RADIUS_M,
    use_cache: bool = True,
    load_roads: bool = True,
) -> dict:
    """
    Load a SMALL local patch around (lat, lon).
    Default dist=100m so first load is fast.
    """
    result = _empty_result(lat, lon, dist)

    if not HAS_OSMNX:
        result["error"] = "OSMnx not installed"
        return result

    key = _cache_key(lat, lon, dist)
    now = time.time()

    if use_cache and key in _cache:
        if now - _cache_timestamps.get(key, 0) < CACHE_TTL:
            cached = dict(_cache[key])
            cached["from_cache"] = True
            return cached

    if use_cache:
        disk_data = _load_disk(key)
        if disk_data is not None:
            _cache[key] = disk_data
            _cache_timestamps[key] = now
            out = dict(disk_data)
            out["from_cache"] = True
            return out

    try:
        # --- Buildings only first (faster than full graph) ---
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

        # --- Roads (optional, slightly slower) ---
        if load_roads:
            try:
                G = ox.graph_from_point(
                    (lat, lon), dist=dist, network_type="walk", simplify=True
                )
                result["road_graph"] = G
                road_lines = []
                for u, v, data in G.edges(data=True):
                    if "geometry" in data:
                        road_lines.append([(p[1], p[0]) for p in data["geometry"].coords])
                    else:
                        y1, x1 = G.nodes[u]["y"], G.nodes[u]["x"]
                        y2, x2 = G.nodes[v]["y"], G.nodes[v]["x"]
                        road_lines.append([(y1, x1), (y2, x2)])
                result["road_lines"] = road_lines
            except Exception as e:
                result["error"] = f"Roads: {str(e)[:60]}"

        result["success"] = True
        result["center"] = (lat, lon)
        result["radius"] = dist
        _cache[key] = result
        _cache_timestamps[key] = now
        _save_disk(key, result)
        return result

    except Exception as e:
        result["error"] = str(e)[:120]
        return result


def merge_map_data(base: dict, extra: dict) -> dict:
    """Merge a newly loaded tile into the existing map data."""
    if not extra or not extra.get("success"):
        return base

    out = dict(base) if base else _empty_result(0, 0, 0)
    out["buildings"] = list(out.get("buildings") or []) + list(extra.get("buildings") or [])
    out["building_coords"] = list(out.get("building_coords") or []) + list(
        extra.get("building_coords") or []
    )
    out["road_lines"] = list(out.get("road_lines") or []) + list(extra.get("road_lines") or [])

    # Prefer keeping an existing graph; if none, take the new one
    if out.get("road_graph") is None and extra.get("road_graph") is not None:
        out["road_graph"] = extra["road_graph"]
    elif out.get("road_graph") is not None and extra.get("road_graph") is not None:
        try:
            import networkx as nx
            out["road_graph"] = nx.compose(out["road_graph"], extra["road_graph"])
        except Exception:
            pass

    out["success"] = True
    # Expand covered radius roughly
    old_r = out.get("radius") or 0
    new_r = extra.get("radius") or 0
    out["radius"] = max(old_r, new_r) + (EXPAND_RADIUS_M // 2)
    if "center" not in out or out["center"] is None:
        out["center"] = extra.get("center")
    return out


def needs_expansion(map_data: dict, lat: float, lon: float) -> bool:
    """True if robot is near the edge of currently loaded area."""
    if not map_data or not map_data.get("success"):
        return True
    center = map_data.get("center")
    radius = map_data.get("radius") or INITIAL_RADIUS_M
    if not center:
        return True
    clat, clon = center
    # approximate metres
    dlat = (lat - clat) * 111320.0
    dlon = (lon - clon) * 111320.0 * max(0.2, abs(__import__("math").cos(__import__("math").radians(lat))))
    dist = (dlat ** 2 + dlon ** 2) ** 0.5
    return dist > max(20.0, radius - EXPAND_TRIGGER_M)


def expand_around(map_data: dict, lat: float, lon: float, dist: int = EXPAND_RADIUS_M) -> dict:
    """Load a small extra tile around current position and merge."""
    extra = load_buildings_and_roads(lat, lon, dist=dist, use_cache=True, load_roads=True)
    return merge_map_data(map_data, extra)


def point_in_buildings(lat: float, lon: float, buildings: list) -> bool:
    if not buildings:
        return False
    pt = Point(lon, lat)
    for poly in buildings:
        try:
            if poly.contains(pt) or poly.intersects(pt.buffer(0.000015)):
                return True
        except Exception:
            continue
    return False


def find_free_spawn(lat: float, lon: float, buildings: list, max_radius_m: float = 60.0) -> Tuple[float, float]:
    """
    If spawn is inside a building, walk outward in a spiral / ring until free.
    Returns a free (lat, lon). If already free, returns original.
    """
    if not point_in_buildings(lat, lon, buildings):
        return lat, lon

    import math
    # try increasing radii and 8 directions
    for radius in [5, 10, 15, 20, 30, 40, 50, 60]:
        if radius > max_radius_m:
            break
        for angle_deg in range(0, 360, 30):
            rad = math.radians(angle_deg)
            d_north = radius * math.cos(rad)
            d_east = radius * math.sin(rad)
            nlat = lat + d_north / 111320.0
            nlon = lon + d_east / (111320.0 * math.cos(math.radians(lat)) + 1e-8)
            if not point_in_buildings(nlat, nlon, buildings):
                return nlat, nlon
    return lat, lon  # fallback: stay put


def get_nearest_road_node(G, lat: float, lon: float):
    if G is None:
        return None
    try:
        return ox.distance.nearest_nodes(G, lon, lat)
    except Exception:
        return None
