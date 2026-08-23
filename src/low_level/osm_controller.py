"""
OSM-aware Low-Level Controller
- Road graph A* routing when possible
- Shapely building collision
- Fallback to reactive movement
"""

from typing import List, Tuple, Optional
import math

try:
    import networkx as nx
    from shapely.geometry import Point
    HAS_NX = True
except ImportError:
    HAS_NX = False

from src.map.osm_loader import point_in_buildings, get_nearest_road_node


class OSMController:
    def __init__(self, lat: float, lon: float, yaw: float = 0.0):
        self.lat = lat
        self.lon = lon
        self.yaw = yaw  # 0 = North, 90 = East
        self.start_lat = lat
        self.start_lon = lon
        self.path: List[Tuple[float, float]] = [(lat, lon)]
        self.buildings = []
        self.road_graph = None

    def reset(self, lat: float, lon: float, yaw: float = 0.0):
        self.lat = lat
        self.lon = lon
        self.yaw = yaw
        self.start_lat = lat
        self.start_lon = lon
        self.path = [(lat, lon)]

    def set_map_data(self, buildings, road_graph):
        self.buildings = buildings or []
        self.road_graph = road_graph

    def _distance_m(self, lat1, lon1, lat2, lon2):
        R = 6371000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def is_collision(self, lat: float, lon: float) -> bool:
        return point_in_buildings(lat, lon, self.buildings)

    def move_forward(self, distance_m: float, step_m: float = 6.0):
        """Reactive forward movement with building avoidance."""
        steps = max(1, int(distance_m / step_m))
        actual = distance_m / steps
        for _ in range(steps):
            rad = math.radians(self.yaw)
            d_north = actual * math.cos(rad)
            d_east  = actual * math.sin(rad)
            dlat = d_north / 111320.0
            dlon = d_east / (111320.0 * math.cos(math.radians(self.lat)) + 1e-8)
            new_lat = self.lat + dlat
            new_lon = self.lon + dlon

            if self.is_collision(new_lat, new_lon):
                # try small turns
                moved = False
                for delta in [25, -25, 50, -50, 80, -80]:
                    test_yaw = (self.yaw + delta) % 360
                    rad_t = math.radians(test_yaw)
                    dn = actual * math.cos(rad_t)
                    de = actual * math.sin(rad_t)
                    tlat = self.lat + dn / 111320.0
                    tlon = self.lon + de / (111320.0 * math.cos(math.radians(self.lat)) + 1e-8)
                    if not self.is_collision(tlat, tlon):
                        self.yaw = test_yaw
                        self.lat = tlat
                        self.lon = tlon
                        self.path.append((tlat, tlon))
                        moved = True
                        break
                if not moved:
                    return  # stuck
            else:
                self.lat = new_lat
                self.lon = new_lon
                self.path.append((new_lat, new_lon))

    def turn_left(self, degrees: float = 90.0):
        self.yaw = (self.yaw - degrees) % 360

    def turn_right(self, degrees: float = 90.0):
        self.yaw = (self.yaw + degrees) % 360

    def return_home(self):
        dlat = self.start_lat - self.lat
        dlon = self.start_lon - self.lon
        self.yaw = (math.degrees(math.atan2(dlon, dlat)) + 360) % 360
        dist = self._distance_m(self.lat, self.lon, self.start_lat, self.start_lon)
        self.move_forward(dist)

    def plan_road_route(self, target_lat: float, target_lon: float) -> List[Tuple[float, float]]:
        """A* on the road graph if available."""
        if self.road_graph is None or not HAS_NX:
            return []
        try:
            start_node = get_nearest_road_node(self.road_graph, self.lat, self.lon)
            end_node = get_nearest_road_node(self.road_graph, target_lat, target_lon)
            if start_node is None or end_node is None:
                return []
            route = nx.shortest_path(self.road_graph, start_node, end_node, weight="length")
            waypoints = []
            for n in route:
                y = self.road_graph.nodes[n]["y"]
                x = self.road_graph.nodes[n]["x"]
                waypoints.append((y, x))
            return waypoints
        except Exception:
            return []

    def follow_waypoints(self, waypoints: List[Tuple[float, float]]):
        """Follow a list of (lat, lon) waypoints."""
        for (tlat, tlon) in waypoints:
            dlat = tlat - self.lat
            dlon = tlon - self.lon
            self.yaw = (math.degrees(math.atan2(dlon, dlat)) + 360) % 360
            dist = self._distance_m(self.lat, self.lon, tlat, tlon)
            self.move_forward(min(dist, 40.0))  # limit per segment
