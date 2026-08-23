"""
OSM-aware Low-Level Controller (NaVILA-style mid-level execution)
- Continuous collision checking along steps
- Stuck recovery (reverse + yaw offset + continue)
- Short-term trajectory + command history
- Full waypoint following with road preference
- Movement scoring
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

        # Short-term history (end-to-end, no hardcoding)
        self.position_history: Deque[Tuple[float, float]] = deque(maxlen=20)
        self.command_history: Deque[str] = deque(maxlen=10)
        self.position_history.append((lat, lon))

        # Stuck tracking
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

    def _segment_has_collision(self, lat1: float, lon1: float, lat2: float, lon2: float, samples: int = 5) -> bool:
        """Continuous collision check: sample points along the segment."""
        for i in range(1, samples + 1):
            t = i / (samples + 1)
            lat = lat1 + t * (lat2 - lat1)
            lon = lon1 + t * (lon2 - lon1)
            if self.is_collision(lat, lon):
                return True
        # also check endpoint
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
        """Dynamic text state for the high-level planner (no hardcoded scenarios)."""
        recent_cmds = list(self.command_history)[-3:] if self.command_history else ["none"]
        recent_collisions = self._consecutive_collisions
        dist = self.total_distance
        return (
            f"heading={self.yaw:.0f}deg, "
            f"pos=({self.lat:.5f},{self.lon:.5f}), "
            f"travelled={dist:.0f}m, "
            f"recent_cmds={recent_cmds}, "
            f"recent_collisions={recent_collisions}, "
            f"total_collisions={self.collision_count}"
        )

    def _try_recover_from_stuck(self, intended_step: float) -> bool:
        """Stuck recovery: reverse a bit + small yaw offset, then try to continue."""
        # Reverse
        reverse_yaw = (self.yaw + 180) % 360
        old_yaw = self.yaw
        self.yaw = reverse_yaw
        ok = self._raw_move(min(12.0, intended_step * 0.6), check_collision=True)
        self.yaw = old_yaw

        # Small random-ish yaw offset to escape local trap
        offset = random.choice([-35, -25, 25, 35, -50, 50])
        self.yaw = (self.yaw + offset) % 360
        ok2 = self._raw_move(min(10.0, intended_step * 0.5), check_collision=True)
        return ok or ok2

    def _raw_move(self, distance_m: float, check_collision: bool = True) -> bool:
        """Single atomic move with continuous collision checking."""
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

    def move_forward(self, distance_m: float, step_m: float = 8.0) -> bool:
        """Move forward with continuous collision checks and stuck recovery."""
        self._record_command(f"move_forward {distance_m:.1f}m")
        steps = max(1, int(distance_m / step_m))
        actual = distance_m / steps
        success_count = 0

        for _ in range(steps):
            ok = self._raw_move(actual, check_collision=True)
            if ok:
                success_count += 1
                continue

            # Local reactive avoidance: try alternate headings
            moved = False
            for delta in [15, -15, 30, -30, 45, -45, 70, -70, 110, -110]:
                test_yaw = (self.yaw + delta) % 360
                old_yaw = self.yaw
                self.yaw = test_yaw
                if self._raw_move(actual, check_collision=True):
                    moved = True
                    success_count += 1
                    break
                self.yaw = old_yaw

            if not moved:
                # Stuck recovery
                if self._consecutive_collisions >= 2 or (
                    len(self._recent_progress) >= 3 and sum(self._recent_progress) < actual * 0.5
                ):
                    recovered = self._try_recover_from_stuck(actual)
                    if recovered:
                        success_count += 1
                        continue
                return False

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

    def follow_waypoints(self, waypoints: List[Tuple[float, float]], max_step_m: float = 100.0):
        """
        Primary method for landmark / OSRM goals.
        Follow the FULL waypoint list with continuous collision checks and stuck recovery.
        Prefers the given road geometry.
        """
        if not waypoints:
            return

        self._record_command(f"follow_waypoints n={len(waypoints)}")

        for (tlat, tlon) in waypoints:
            for _ in range(40):  # safety cap per waypoint
                dist = self._distance_m(self.lat, self.lon, tlat, tlon)
                if dist < 20:
                    break

                dlat = tlat - self.lat
                dlon = tlon - self.lon
                self.yaw = (math.degrees(math.atan2(dlon, dlat)) + 360) % 360

                step = min(max_step_m, dist)
                ok = self.move_forward(step, step_m=min(12.0, step))
                if not ok:
                    # try one recovery then continue to next waypoint rather than freeze
                    self._try_recover_from_stuck(step)
                    break

        # Final approach to last point
        if waypoints:
            tlat, tlon = waypoints[-1]
            dist = self._distance_m(self.lat, self.lon, tlat, tlon)
            if dist > 25:
                dlat = tlat - self.lat
                dlon = tlon - self.lon
                self.yaw = (math.degrees(math.atan2(dlon, dlat)) + 360) % 360
                self.move_forward(min(dist, 180.0), step_m=10.0)
