"""
OSM Loader – Buildings (obstacles) + Road Graph
Caches results in memory to avoid repeated Overpass calls.
"""

from typing import Tuple, List, Optional, Dict
import math

try:
    import osmnx as ox
    import networkx as nx
    from shapely.geometry import Point, Polygon, LineString
    HAS_OSMNX = True
except ImportError:
    HAS_OSMNX = False
    ox = None
    nx = None

# Simple in-memory cache: key = (round(lat,4), round(lon,4), dist)
_cache: Dict[Tuple, dict] = {}


def _cache_key(lat: float, lon: float, dist: int) -> Tuple:
    return (round(lat, 4), round(lon, 4), dist)


def load_buildings_and_roads(
    lat: float,
    lon: float,
    dist: int = 350,
    use_cache: bool = True
) -> dict:
    """
    Returns:
    {
        "buildings": list of shapely Polygons,
        "building_coords": list of list[(lat,lon)] for Folium,
        "road_graph": networkx MultiDiGraph or None,
        "road_lines": list of list[(lat,lon)] for Folium,
        "success": bool,
        "error": str or None
    }
    """
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
    if use_cache and key in _cache:
        return _cache[key]

    try:
        # ----- Buildings (obstacles) -----
        bldg_gdf = ox.features_from_point((lat, lon), tags={"building": True}, dist=dist)
        buildings = []
        building_coords = []
        if bldg_gdf is not None and not bldg_gdf.empty:
            for geom in bldg_gdf.geometry:
                if geom is None:
                    continue
                if geom.geom_type == "Polygon":
                    buildings.append(geom)
                    coords = [(p[1], p[0]) for p in geom.exterior.coords]  # (lat, lon)
                    building_coords.append(coords)
                elif geom.geom_type == "MultiPolygon":
                    for poly in geom.geoms:
                        buildings.append(poly)
                        coords = [(p[1], p[0]) for p in poly.exterior.coords]
                        building_coords.append(coords)

        result["buildings"] = buildings
        result["building_coords"] = building_coords

        # ----- Road graph (for A*) -----
        try:
            G = ox.graph_from_point((lat, lon), dist=dist, network_type="walk", simplify=True)
            result["road_graph"] = G

            # Also extract simple lines for visualization
            road_lines = []
            for u, v, data in G.edges(data=True):
                if "geometry" in data:
                    coords = [(p[1], p[0]) for p in data["geometry"].coords]
                    road_lines.append(coords)
                else:
                    # fallback straight line
                    y1, x1 = G.nodes[u]["y"], G.nodes[u]["x"]
                    y2, x2 = G.nodes[v]["y"], G.nodes[v]["x"]
                    road_lines.append([(y1, x1), (y2, x2)])
            result["road_lines"] = road_lines
        except Exception as e:
            result["error"] = f"Road graph failed: {str(e)[:100]}"

        result["success"] = True
        _cache[key] = result
        return result

    except Exception as e:
        result["error"] = str(e)[:150]
        return result


def point_in_buildings(lat: float, lon: float, buildings: list) -> bool:
    """Check if a point collides with any building polygon."""
    if not buildings:
        return False
    pt = Point(lon, lat)  # shapely uses (x=lon, y=lat)
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
