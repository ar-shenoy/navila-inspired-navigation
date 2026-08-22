"""
NaVILA-Lite – Map-based Hierarchical Navigation Demo
Uses interactive maps (Folium) + Hybrid VLM/Heuristic high-level planner
+ RL-inspired low-level controller.
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
import math
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple
import time

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
            return f"{self.action.replace('_', ' ')} {self.value:.2f}m"
        return self.action.replace("_", " ")


@dataclass
class RobotState:
    lat: float
    lon: float
    yaw: float = 0.0  # degrees for simplicity on map


# -------------------------------------------------
# Hybrid High-Level Planner (Heuristic strong + VLM ready)
# -------------------------------------------------
class HybridPlanner:
    def __init__(self):
        self.forward_words = ["forward", "ahead", "straight", "go", "move", "walk", "advance"]
        self.left_words = ["left"]
        self.right_words = ["right"]
        self.stop_words = ["stop", "halt", "wait", "stay"]

    def parse(self, instruction: str) -> MidLevelCommand:
        text = instruction.lower().strip()

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

        distance = value if value is not None else 0.6
        if distance > 5:
            distance /= 100.0
        return MidLevelCommand("move_forward", distance, "heuristic")


# -------------------------------------------------
# Simple Map Controller
# -------------------------------------------------
class MapController:
    def __init__(self, start_lat=12.9716, start_lon=77.5946):  # Bangalore default
        self.state = RobotState(lat=start_lat, lon=start_lon, yaw=0.0)
        self.path: List[Tuple[float, float]] = [(start_lat, start_lon)]
        self.obstacles = []  # list of (lat, lon, radius_meters)

    def reset(self, lat, lon):
        self.state = RobotState(lat=lat, lon=lon, yaw=0.0)
        self.path = [(lat, lon)]

    def set_obstacles(self, obstacles):
        self.obstacles = obstacles

    def _move(self, distance_m: float):
        # Approximate conversion (good enough for small movements)
        # 1 degree latitude ≈ 111_320 meters
        dy = distance_m * math.cos(math.radians(self.state.yaw))
        dx = distance_m * math.sin(math.radians(self.state.yaw))

        dlat = dy / 111320.0
        dlon = dx / (111320.0 * math.cos(math.radians(self.state.lat)))

        self.state.lat += dlat
        self.state.lon += dlon
        self.path.append((self.state.lat, self.state.lon))

    def execute(self, cmd: MidLevelCommand):
        if cmd.action == "stop":
            return

        if cmd.action == "move_forward":
            dist = cmd.value if cmd.value else 0.5
            # Move in small steps for smoother path
            steps = max(1, int(dist / 0.15))
            step = dist / steps
            for _ in range(steps):
                self._move(step)

        elif cmd.action == "turn_left":
            angle = cmd.value if cmd.value else 30.0
            self.state.yaw = (self.state.yaw + angle) % 360

        elif cmd.action == "turn_right":
            angle = cmd.value if cmd.value else 30.0
            self.state.yaw = (self.state.yaw - angle) % 360


# -------------------------------------------------
# Streamlit App
# -------------------------------------------------
st.set_page_config(page_title="NaVILA-Lite Map Navigation", page_icon="🗺️", layout="wide")

st.title("🗺️ NaVILA-Lite – Map-based Hierarchical Navigation")
st.markdown("""
**Hierarchical VLA-style navigation on real maps**  
High-level language planner → Mid-level commands → Robot movement on interactive map
""")

# Sidebar
with st.sidebar:
    st.header("Controls")
    location = st.selectbox("Start Location", [
        "Bangalore (MG Road)",
        "Campus Area",
        "Open Area"
    ])

    instruction = st.text_input("Language Instruction", value="Move forward 40 meters")
    col1, col2 = st.columns(2)
    execute_btn = col1.button("Execute", type="primary")
    reset_btn = col2.button("Reset")

# Session state
if "controller" not in st.session_state:
    st.session_state.controller = MapController()
    st.session_state.planner = HybridPlanner()
    st.session_state.history = []

# Location presets
locations = {
    "Bangalore (MG Road)": (12.9750, 77.6060),
    "Campus Area": (12.9700, 77.5900),
    "Open Area": (12.9800, 77.6000),
}

if reset_btn:
    lat, lon = locations[location]
    st.session_state.controller.reset(lat, lon)
    st.session_state.history = []
    st.rerun()

if execute_btn and instruction.strip():
    cmd = st.session_state.planner.parse(instruction)
    st.session_state.controller.execute(cmd)
    st.session_state.history.append({
        "instruction": instruction,
        "command": str(cmd),
        "source": cmd.source
    })

# Create map
ctrl = st.session_state.controller
m = folium.Map(location=[ctrl.state.lat, ctrl.state.lon], zoom_start=17, tiles="OpenStreetMap")

# Draw path
if len(ctrl.path) > 1:
    folium.PolyLine(ctrl.path, color="blue", weight=5, opacity=0.8).add_to(m)

# Robot marker
folium.Marker(
    [ctrl.state.lat, ctrl.state.lon],
    popup=f"Yaw: {ctrl.state.yaw:.1f}°",
    icon=folium.Icon(color="green", icon="info-sign")
).add_to(m)

# Start marker
if ctrl.path:
    folium.CircleMarker(
        ctrl.path[0], radius=6, color="green", fill=True, fill_color="green"
    ).add_to(m)

# Show map
st_folium(m, width=900, height=550)

# Info panels
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Current State")
    st.write(f"**Latitude:** {ctrl.state.lat:.6f}")
    st.write(f"**Longitude:** {ctrl.state.lon:.6f}")
    st.write(f"**Yaw:** {ctrl.state.yaw:.1f}°")

with col_b:
    st.subheader("Command History")
    if st.session_state.history:
        for h in reversed(st.session_state.history[-5:]):
            st.markdown(f"- `{h['instruction']}` → **{h['command']}** ({h['source']})")
    else:
        st.info("No commands yet.")

st.markdown("---")
st.caption("NaVILA-Lite · Hierarchical design inspired by NaVILA (RSS 2025) · Map-based demonstration")
