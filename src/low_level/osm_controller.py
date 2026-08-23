"""
OSM-aware Low-Level Controller — fast traversal + solid avoidance.
"""

from typing import List, Tuple, Optional, Deque
from collections import deque
import math
import random

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

        self.position_history: Deque[Tuple[float, float]] = deque(maxlen=20)
        self.command_history: Deque[str] = deque(maxlen=10)
        self.position_history.append((lat, lon))
        self._recent_progress: Deque[float] = deque(maxlen=5)
        self._consecutive_collisions = 0

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
        self.position_history.clear()
        self.command_history.clear()
        self.position_history.append((lat, lon))
        self._recent_progress.clear()
        self._consecutive_collisions = 0

    def set_map_data(self, buildings, road_graph):
        self.buildings = buildings or []
        self.road_graph = road_graph

    def _distance_m(self, lat1, lon1, lat2, lon2):
        R = 6371000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def is_collision(self, lat: float, lon: float) -> bool:
        return point_in_buildings(lat, lon, self.buildings)

    def _segment_has_collision(self, lat1, lon1, lat2, lon2, samples: int = 2) -> bool:
        """Light continuous check (2 midpoints) — fast enough for interactive use."""
        for i in range(1, samples + 1):
            t = i / (samples + 1)
            if self.is_collision(lat1 + t * (lat2 - lat1), lon1 + t * (lon2 - lon1)):
                return True
        return self.is_collision(lat2, lon2)

    def _update_score(self, dist_moved: float, collided: bool):
        self.total_distance += dist_moved
        if collided:
            self.collision_count += 1
            self.score -= 2.0
            self._consecutive_collisions += 1
        else:
            self.score += dist_moved * 0.05
            self._consecutive_collisions = 0

    def _record_position(self):
        self.position_history.append((self.lat, self.lon))
        self.path.append((self.lat, self.lon))

    def _record_command(self, cmd: str):
        self.command_history.append(cmd)

    def get_state_summary(self) -> str:
        recent_cmds = list(self.command_history)[-3:] if self.command_history else ["none"]
        return (
            f"heading={self.yaw:.0f}deg, "
            f"pos=({self.lat:.5f},{self.lon:.5f}), "
            f"travelled={self.total_distance:.0f}m, "
            f"recent_cmds={recent_cmds}, "
            f"collisions={self.collision_count}"
        )

    def _try_recover_from_stuck(self, intended_step: float) -> bool:
        reverse_yaw = (self.yaw + 180) % 360
        old_yaw = self.yaw
        self.yaw = reverse_yaw
        ok = self._raw_move(min(10.0, intended_step * 0.5), check_collision=True)
        self.yaw = old_yaw
        self.yaw = (self.yaw + random.choice([-30, 30, -45, 45])) % 360
        ok2 = self._raw_move(min(8.0, intended_step * 0.4), check_collision=True)
        return ok or ok2

    def _raw_move(self, distance_m: float, check_collision: bool = True) -> bool:
        if distance_m <= 0:
            return True
        rad = math.radians(self.yaw)
        d_north = distance_m * math.cos(rad)
        d_east = distance_m * math.sin(rad)
        dlat = d_north / 111320.0
        dlon = d_east / (111320.0 * math.cos(math.radians(self.lat)) + 1e-8)
        new_lat = self.lat + dlat
        new_lon = self.lon + dlon

        if check_collision and self._segment_has_collision(self.lat, self.lon, new_lat, new_lon):
            self._update_score(0, collided=True)
            return False

        self.lat = new_lat
        self.lon = new_lon
        self._record_position()
        self._update_score(distance_m, collided=False)
        self._recent_progress.append(distance_m)
        return True

    def move_forward(self, distance_m: float, step_m: float = 20.0) -> bool:
        """Faster default step (20m) for interactive demo."""
        self._record_command(f"move_forward {distance_m:.1f}m")
        steps = max(1, int(math.ceil(distance_m / max(step_m, 1.0))))
        actual = distance_m / steps
        success_count = 0

        for _ in range(steps):
            if self._raw_move(actual, check_collision=True):
                success_count += 1
                continue

            moved = False
            for delta in [20, -20, 40, -40, 70, -70]:
                old_yaw = self.yaw
                self.yaw = (old_yaw + delta) % 360
                if self._raw_move(actual, check_collision=True):
                    moved = True
                    success_count += 1
                    break
                self.yaw = old_yaw

            if not moved:
                if self._consecutive_collisions >= 2:
                    if self._try_recover_from_stuck(actual):
                        success_count += 1
                        continue
                return success_count > 0

        return success_count > 0

    def turn_left(self, degrees: float = 90.0):
        self.yaw = (self.yaw - degrees) % 360
        self._record_command(f"turn_left {degrees:.0f}deg")

    def turn_right(self, degrees: float = 90.0):
        self.yaw = (self.yaw + degrees) % 360
        self._record_command(f"turn_right {degrees:.0f}deg")

    def return_home(self):
        self._record_command("return_home")
        dlat = self.start_lat - self.lat
        dlon = self.start_lon - self.lon
        self.yaw = (math.degrees(math.atan2(dlon, dlat)) + 360) % 360
        dist = self._distance_m(self.lat, self.lon, self.start_lat, self.start_lon)
        self.move_forward(dist, step_m=25.0)

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

    def follow_waypoints(self, waypoints: List[Tuple[float, float]], max_step_m: float = 80.0):
        """Fast waypoint following — fewer micro-steps, light collision checks."""
        if not waypoints:
            return

        self._record_command(f"follow_waypoints n={len(waypoints)}")

        # Downsample very long routes for speed
        if len(waypoints) > 40:
            step = max(1, len(waypoints) // 40)
            waypoints = waypoints[::step]
            if waypoints[-1] != waypoints[-1]:
                pass

        for (tlat, tlon) in waypoints:
            for _ in range(12):  # fewer iterations per waypoint
                dist = self._distance_m(self.lat, self.lon, tlat, tlon)
                if dist < 30:
                    break
                dlat = tlat - self.lat
                dlon = tlon - self.lon
                self.yaw = (math.degrees(math.atan2(dlon, dlat)) + 360) % 360
                step = min(max_step_m, dist)
                ok = self.move_forward(step, step_m=min(25.0, step))
                if not ok:
                    self._try_recover_from_stuck(step)
                    break

        if waypoints:
            tlat, tlon = waypoints[-1]
            dist = self._distance_m(self.lat, self.lon, tlat, tlon)
            if dist > 35:
                dlat = tlat - self.lat
                dlon = tlon - self.lon
                self.yaw = (math.degrees(math.atan2(dlon, dlat)) + 360) % 360
                self.move_forward(min(dist, 150.0), step_m=25.0)
