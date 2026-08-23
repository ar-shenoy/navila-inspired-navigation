"""
OSM Loader with in-memory + disk caching for reliability.
Buildings = obstacles, roads = preferred paths.
Fully on-demand / end-to-end (no hardcoded maps).
"""

from typing import Tuple, List, Dict, Optional
import time
import os
import pickle
from pathlib import Path

try:
    import osmnx as ox
    import networkx as nx
    from shapely.geometry import Point
    HAS_OSMNX = True
    ox.settings.timeout = 45
    ox.settings.overpass_rate_limit = True
except ImportError:
    HAS_OSMNX = False
    ox = None

# In-memory cache
_cache: Dict[Tuple, dict] = {}
_cache_timestamps: Dict[Tuple, float] = {}
CACHE_TTL = 600  # 10 minutes

# Disk cache directory (created on demand)
DISK_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".osm_cache"
DISK_CACHE_TTL = 3600 * 6  # 6 hours


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
        path = _disk_path(key)
        # Do not pickle the full NetworkX graph if it is huge; keep a lightweight flag
        to_save = dict(data)
        # road_graph can be large; we still keep it for quality when possible
        with open(path, "wb") as f:
            pickle.dump(to_save, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass


def load_buildings_and_roads(lat: float, lon: float, dist: int = 300, use_cache: bool = True) -> dict:
    result = {
        "buildings": [],
        "building_coords": [],
        "road_graph": None,
        "road_lines": [],
        "success": False,
        "error": None,
        "from_cache": False,
    }

    if not HAS_OSMNX:
        result["error"] = "OSMnx not installed"
        return result

    key = _cache_key(lat, lon, dist)
    now = time.time()

    # 1) In-memory cache
    if use_cache and key in _cache:
        if now - _cache_timestamps.get(key, 0) < CACHE_TTL:
            cached = _cache[key].copy()
            cached["from_cache"] = True
            return cached

    # 2) Disk cache
    if use_cache:
        disk_data = _load_disk(key)
        if disk_data is not None:
            _cache[key] = disk_data
            _cache_timestamps[key] = now
            disk_data = disk_data.copy()
            disk_data["from_cache"] = True
            return disk_data

    try:
        # Buildings
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

        # Roads
        try:
            G = ox.graph_from_point((lat, lon), dist=dist, network_type="walk", simplify=True)
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
            result["error"] = f"Road graph: {str(e)[:80]}"

        result["success"] = True
        _cache[key] = result
        _cache_timestamps[key] = now
        _save_disk(key, result)
        return result

    except Exception as e:
        result["error"] = str(e)[:120]
        return result


def point_in_buildings(lat: float, lon: float, buildings: list) -> bool:
    if not buildings:
        return False
    pt = Point(lon, lat)
    for poly in buildings:
        try:
            if poly.contains(pt) or poly.intersects(pt.buffer(0.00002)):
                return True
        except Exception:
            continue
    return False


def get_nearest_road_node(G, lat: float, lon: float):
    if G is None:
        return None
    try:
        return ox.distance.nearest_nodes(G, lon, lat)
    except Exception:
        return None
