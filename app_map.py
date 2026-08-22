"""
NaVILA-Lite – Map-based Hierarchical Navigation
Upgraded version with:
- Multi-command instructions
- Longer distance support (including 1km+)
- Taiwan + more locations
- Basic obstacle avoidance
- Fixed environments
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
import math
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple

# -------------------------------------------------
# Data structures
# -------------------------------------------------
@dataclass
class MidLevelCommand:
    action: str
    value: Optional[float] = None
    source: str = "heuristic"

    def __str__(self):
        if self.action == "stop":
            return "stop"
        if self.value is not None:
            if "turn" in self.action:
                return f"{self.action.replace('_', ' ')} {self.value:.0f}°"
            return f"{self.action.replace('_', ' ')} {self.value:.1f}m"
        return self.action.replace("_", " ")


@dataclass
class RobotState:
    lat: float
    lon: float
    yaw: float = 0.0  # degrees


# -------------------------------------------------
# Hybrid Planner with multi-command support
# -------------------------------------------------
class HybridPlanner:
    def __init__(self):
        self.forward_words = ["forward", "ahead", "straight", "go", "move", "walk", "advance"]
        self.left_words = ["left"]
        self.right_words = ["right"]
        self.stop_words = ["stop", "halt", "wait", "stay"]

    def _parse_single(self, text: str) -> MidLevelCommand:
        text = text.lower().strip()

        if any(w in text for w in self.stop_words):
            return MidLevelCommand("stop", source="heuristic")

        numbers = re.findall(r"(\d+\.?\d*)", text)
        value = float(numbers[0]) if numbers else None

        if any(w in text for w in self.left_words):
            angle = value if value is not None else 30.0
            return MidLevelCommand("turn_left", angle, "heuristic")

        if any(w in text for w in self.right_words):
            angle = value if value is not None else 30.0
            return MidLevelCommand("turn_right", angle, "heuristic")

        # Distance handling (support meters and km)
        distance = value if value is not None else 20.0
        if "km" in text or distance >= 1000:
            if "km" in text:
                distance = value * 1000 if value else 1000

        return MidLevelCommand("move_forward", distance, "heuristic")

    def parse_multiple(self, instruction: str) -> List[MidLevelCommand]:
        """
        Support multiple commands in one sentence.
        """
        parts = re.split(r",| and | then |\.", instruction.lower())
        parts = [p.strip() for p in parts if p.strip()]

        commands = []
        for part in parts:
            if any(w in part for w in self.forward_words + self.left_words + self.right_words + self.stop_words):
                cmd = self._parse_single(part)
                commands.append(cmd)

        if not commands:
            commands.append(self._parse_single(instruction))

        return commands


# -------------------------------------------------
# Map Controller with basic obstacle avoidance
# -------------------------------------------------
class MapController:
    def __init__(self, start_lat=25.0330, start_lon=121.5654):
        self.state = RobotState(lat=start_lat, lon=start_lon, yaw=0.0)
        self.path: List[Tuple[float, float]] = [(start_lat, start_lon)]
        self.obstacles: List[Tuple[float, float, float]] = []

    def reset(self, lat, lon, yaw=0.0):
        self.state = RobotState(lat=lat, lon=lon, yaw=yaw)
        self.path = [(lat, lon)]

    def set_obstacles(self, obstacles):
        self.obstacles = obstacles

    def _distance_m(self, lat1, lon1, lat2, lon2):
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def _is_collision(self, lat, lon, robot_radius=3.0):
        for olat, olon, radius in self.obstacles:
            if self._distance_m(lat, lon, olat, olon) < (radius + robot_radius):
                return True
        return False

    def _move_step(self, distance_m: float):
        dy = distance_m * math.cos(math.radians(self.state.yaw))
        dx = distance_m * math.sin(math.radians(self.state.yaw))

        dlat = dy / 111320.0
        dlon = dx / (111320.0 * math.cos(math.radians(self.state.lat)) + 1e-8)

        new_lat = self.state.lat + dlat
        new_lon = self.state.lon + dlon

        if self._is_collision(new_lat, new_lon):
            for delta in [25, -25, 45, -45, 70, -70]:
                test_yaw = (self.state.yaw + delta) % 360
                dy2 = distance_m * math.cos(math.radians(test_yaw))
                dx2 = distance_m * math.sin(math.radians(test_yaw))
                tlat = self.state.lat + dy2 / 111320.0
                tlon = self.state.lon + dx2 / (111320.0 * math.cos(math.radians(self.state.lat)) + 1e-8)
                if not self._is_collision(tlat, tlon):
                    self.state.yaw = test_yaw
                    self.state.lat = tlat
                    self.state.lon = tlon
                    self.path.append((tlat, tlon))
                    return
            return

        self.state.lat = new_lat
        self.state.lon = new_lon
        self.path.append((new_lat, new_lon))

    def execute(self, cmd: MidLevelCommand):
        if cmd.action == "stop":
            return

        if cmd.action == "move_forward":
            dist = cmd.value if cmd.value is not None else 20.0
            step_size = 4.0
            steps = max(1, int(dist / step_size))
            actual_step = dist / steps
            for _ in range(steps):
                self._move_step(actual_step)

        elif cmd.action == "turn_left":
            angle = cmd.value if cmd.value is not None else 30.0
            self.state.yaw = (self.state.yaw + angle) % 360

        elif cmd.action == "turn_right":
            angle = cmd.value if cmd.value is not None else 30.0
            self.state.yaw = (self.state.yaw - angle) % 360


# -------------------------------------------------
# Streamlit App
# -------------------------------------------------
st.set_page_config(page_title="NaVILA-Lite Map Navigation", page_icon="🗺️", layout="wide")

st.title("🗺️ NaVILA-Lite – Map-based Hierarchical Navigation")
st.markdown("""
**NaVILA-style hierarchical navigation on real maps**  
High-level language → Mid-level commands → Movement + basic obstacle avoidance
""")

LOCATIONS = {
    "Taipei 101": (25.0330, 121.5654),
    "National Taiwan University": (25.0170, 121.5395),
    "Taipei Main Station": (25.0478, 121.5170),
    "Kaohsiung": (22.6273, 120.3014),
    "Tainan": (22.9999, 120.2269),
    "Bangalore MG Road": (12.9750, 77.6060),
    "Open Field (Test)": (25.0500, 121.5800),
}

with st.sidebar:
    st.header("Controls")
    location_name = st.selectbox("Start Location", list(LOCATIONS.keys()))
    instruction = st.text_area(
        "Language Instruction(s)",
        value="Move forward 150 meters and turn left 90 degrees",
        height=100,
        help="You can write multiple commands, e.g.: move 200m then turn left 90 then move 300m"
    )
    col1, col2 = st.columns(2)
    execute_btn = col1.button("Execute", type="primary")
    reset_btn = col2.button("Reset")

if "controller" not in st.session_state:
    lat, lon = LOCATIONS["Taipei 101"]
    st.session_state.controller = MapController(lat, lon)
    st.session_state.planner = HybridPlanner()
    st.session_state.history = []

if reset_btn:
    lat, lon = LOCATIONS[location_name]
    st.session_state.controller.reset(lat, lon)
    st.session_state.history = []
    st.rerun()

if execute_btn and instruction.strip():
    commands = st.session_state.planner.parse_multiple(instruction)
    for cmd in commands:
        st.session_state.controller.execute(cmd)
        st.session_state.history.append({
            "instruction": instruction,
            "command": str(cmd),
            "source": cmd.source
        })

ctrl = st.session_state.controller
if location_name == "Taipei 101":
    ctrl.set_obstacles([
        (25.0340, 121.5660, 25),
        (25.0320, 121.5645, 20),
    ])
else:
    ctrl.set_obstacles([])

m = folium.Map(location=[ctrl.state.lat, ctrl.state.lon], zoom_start=16, tiles="OpenStreetMap")

if len(ctrl.path) > 1:
    folium.PolyLine(ctrl.path, color="#0066ff", weight=6, opacity=0.85).add_to(m)

for olat, olon, rad in ctrl.obstacles:
    folium.Circle(
        location=[olat, olon],
        radius=rad,
        color="red",
        fill=True,
        fill_opacity=0.35,
        popup="Obstacle"
    ).add_to(m)

if ctrl.path:
    folium.CircleMarker(ctrl.path[0], radius=7, color="green", fill=True, fill_color="lime").add_to(m)

folium.Marker(
    [ctrl.state.lat, ctrl.state.lon],
    popup=f"Yaw: {ctrl.state.yaw:.1f}°",
    icon=folium.Icon(color="green", icon="arrow-up")
).add_to(m)

st_folium(m, width=950, height=580)

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Robot State")
    st.metric("Latitude", f"{ctrl.state.lat:.6f}")
    st.metric("Longitude", f"{ctrl.state.lon:.6f}")
    st.metric("Yaw", f"{ctrl.state.yaw:.1f}°")

with col_b:
    st.subheader("Executed Commands")
    if st.session_state.history:
        for h in reversed(st.session_state.history[-6:]):
            st.markdown(f"`{h['command']}`  \n<span style='color:gray;font-size:0.85em'>({h['source']})</span>", unsafe_allow_html=True)
    else:
        st.info("No commands executed yet.")

st.markdown("---")
st.caption("NaVILA-Lite · Hierarchical VLA-style navigation on real maps · Inspired by NaVILA (RSS 2025)")
