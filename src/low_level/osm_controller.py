"""
OSM-aware Low-Level Controller
- Full waypoint following (no early stop)
- Reactive local avoidance
- Movement scoring
"""

from typing import List, Tuple, Optional
import math

try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False

from src.map.osm_loader import point_in_buildings, get_nearest_road_node


class OSMController:
    def __init__(self, lat: float, lon: float, yaw: float = 0.0):
        self.lat = lat
        self.lon = lon
        self.yaw = yaw
        self.start_lat = lat
        self.start_lon = lon
        self.path: List[Tuple[float, float]] = [(lat, lon)]
        self.buildings = []
        self.road_graph = None
        self.total_distance = 0.0
        self.collision_count = 0
        self.score = 0.0

    def reset(self, lat: float, lon: float, yaw: float = 0.0):
        self.lat = lat
        self.lon = lon
        self.yaw = yaw
        self.start_lat = lat
        self.start_lon = lon
        self.path = [(lat, lon)]
        self.total_distance = 0.0
        self.collision_count = 0
        self.score = 0.0

    def set_map_data(self, buildings, road_graph):
        self.buildings = buildings or []
        self.road_graph = road_graph

    def _distance_m(self, lat1, lon1, lat2, lon2):
        R = 6371000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def is_collision(self, lat: float, lon: float) -> bool:
        return point_in_buildings(lat, lon, self.buildings)

    def _update_score(self, dist_moved: float, collided: bool):
        self.total_distance += dist_moved
        if collided:
            self.collision_count += 1
            self.score -= 2.0
        else:
            self.score += dist_moved * 0.05

    def move_forward(self, distance_m: float, step_m: float = 8.0):
        steps = max(1, int(distance_m / step_m))
        actual = distance_m / steps
        for _ in range(steps):
            rad = math.radians(self.yaw)
            d_north = actual * math.cos(rad)
            d_east = actual * math.sin(rad)
            dlat = d_north / 111320.0
            dlon = d_east / (111320.0 * math.cos(math.radians(self.lat)) + 1e-8)
            new_lat = self.lat + dlat
            new_lon = self.lon + dlon

            if self.is_collision(new_lat, new_lon):
                self._update_score(0, collided=True)
                moved = False
                for delta in [20, -20, 40, -40, 70, -70, 110, -110]:
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
                        self._update_score(actual, collided=False)
                        moved = True
                        break
                if not moved:
                    return False
            else:
                self.lat = new_lat
                self.lon = new_lon
                self.path.append((new_lat, new_lon))
                self._update_score(actual, collided=False)
        return True

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
        if self.road_graph is None or not HAS_NX:
            return []
        try:
            start_node = get_nearest_road_node(self.road_graph, self.lat, self.lon)
            end_node = get_nearest_road_node(self.road_graph, target_lat, target_lon)
            if start_node is None or end_node is None:
                return []
            route = nx.shortest_path(self.road_graph, start_node, end_node, weight="length")
            return [(self.road_graph.nodes[n]["y"], self.road_graph.nodes[n]["x"]) for n in route]
        except Exception:
            return []

    def follow_waypoints(self, waypoints: List[Tuple[float, float]], max_step_m: float = 120.0):
        """
        Follow the FULL waypoint list until the end.
        No early exit except if completely stuck.
        """
        if not waypoints:
            return

        for (tlat, tlon) in waypoints:
            # Keep stepping toward this waypoint until close enough
            for _ in range(30):  # safety cap per waypoint
                dist = self._distance_m(self.lat, self.lon, tlat, tlon)
                if dist < 25:  # close enough → next waypoint
                    break

                dlat = tlat - self.lat
                dlon = tlon - self.lon
                self.yaw = (math.degrees(math.atan2(dlon, dlat)) + 360) % 360

                step = min(max_step_m, dist)
                ok = self.move_forward(step)
                if not ok:
                    # slightly larger step attempt with different yaw already handled inside
                    # if still stuck, skip to next waypoint rather than freezing whole route
                    break

        # Final snap toward last point if still a bit away
        if waypoints:
            tlat, tlon = waypoints[-1]
            dist = self._distance_m(self.lat, self.lon, tlat, tlon)
            if dist > 30:
                dlat = tlat - self.lat
                dlon = tlon - self.lon
                self.yaw = (math.degrees(math.atan2(dlon, dlat)) + 360) % 360
                self.move_forward(min(dist, 200.0))
