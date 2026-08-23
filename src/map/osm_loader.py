"""
OSM Loader with improved caching and timeout handling.
"""

from typing import Tuple, List, Dict, Optional
import time

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

_cache: Dict[Tuple, dict] = {}
_cache_timestamps: Dict[Tuple, float] = {}
CACHE_TTL = 600  # 10 minutes

def _cache_key(lat: float, lon: float, dist: int) -> Tuple:
    return (round(lat, 4), round(lon, 4), dist)

def load_buildings_and_roads(lat: float, lon: float, dist: int = 300, use_cache: bool = True) -> dict:
    result = {
        "buildings": [],
        "building_coords": [],
        "road_graph": None,
        "road_lines": [],
        "success": False,
        "error": None
    }

    if not HAS_OSMNX:
        result["error"] = "OSMnx not installed"
        return result

    key = _cache_key(lat, lon, dist)
    now = time.time()
    if use_cache and key in _cache:
        if now - _cache_timestamps.get(key, 0) < CACHE_TTL:
            return _cache[key]

    try:
        # Buildings
        bldg_gdf = ox.features_from_point((lat, lon), tags={"building": True}, dist=dist)
        buildings, building_coords = [], []
        if bldg_gdf is not None and not bldg_gdf.empty:
            for geom in bldg_gdf.geometry:
                if geom is None: continue
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
