"""
NaVILA-Lite - Clean & Reliable Map Navigation
Focus: Correct movement direction + fast startup
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
import math
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple

# -------------------------------------------------
# Data
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
    yaw: float = 0.0  # 0 = North, 90 = East, 180 = South, 270 = West

# -------------------------------------------------
# Planner
# -------------------------------------------------
class HybridPlanner:
    def __init__(self):
        self.forward_words = ["forward", "ahead", "straight", "go", "move", "walk", "advance"]
        self.left_words = ["left"]
        self.right_words = ["right"]
        self.stop_words = ["stop", "halt", "wait"]

    def _parse_single(self, text: str) -> MidLevelCommand:
        text = text.lower().strip()
        if any(w in text for w in self.stop_words):
            return MidLevelCommand("stop")

        numbers = re.findall(r"(\d+\.?\d*)", text)
        value = float(numbers[0]) if numbers else None

        if any(w in text for w in self.left_words):
            return MidLevelCommand("turn_left", value if value is not None else 90.0)
        if any(w in text for w in self.right_words):
            return MidLevelCommand("turn_right", value if value is not None else 90.0)

        distance = value if value is not None else 30.0
        if "km" in text:
            distance = (value if value else 1.0) * 1000.0
        return MidLevelCommand("move_forward", distance)

    def parse_multiple(self, instruction: str) -> List[MidLevelCommand]:
        parts = re.split(r",| and | then |\.", instruction.lower())
        parts = [p.strip() for p in parts if p.strip()]
        cmds = []
        for p in parts:
            if any(w in p for w in self.forward_words + self.left_words + self.right_words + self.stop_words):
                cmds.append(self._parse_single(p))
        if not cmds:
            cmds.append(self._parse_single(instruction))
        return cmds

# -------------------------------------------------
# Controller - CORRECTED MATH
# -------------------------------------------------
class MapController:
    def __init__(self, lat, lon, yaw=0.0):
        self.state = RobotState(lat, lon, yaw)
        self.path = [(lat, lon)]

    def reset(self, lat, lon, yaw=0.0):
        self.state = RobotState(lat, lon, yaw)
        self.path = [(lat, lon)]

    def _move_forward(self, distance_m: float):
        """
        yaw = 0   → North
        yaw = 90  → East
        yaw = 180 → South
        yaw = 270 → West
        """
        rad = math.radians(self.state.yaw)

        # North and East components
        d_north = distance_m * math.cos(rad)
        d_east  = distance_m * math.sin(rad)

        dlat = d_north / 111320.0
        dlon = d_east  / (111320.0 * math.cos(math.radians(self.state.lat)) + 1e-8)

        self.state.lat += dlat
        self.state.lon += dlon
        self.path.append((self.state.lat, self.state.lon))

    def execute(self, cmd: MidLevelCommand):
        if cmd.action == "stop":
            return

        if cmd.action == "move_forward":
            dist = cmd.value if cmd.value is not None else 30.0
            # Move in small steps for smoother path
            step = 8.0
            steps = max(1, int(dist / step))
            actual = dist / steps
            for _ in range(steps):
                self._move_forward(actual)

        elif cmd.action == "turn_left":
            angle = cmd.value if cmd.value is not None else 90.0
            self.state.yaw = (self.state.yaw - angle) % 360

        elif cmd.action == "turn_right":
            angle = cmd.value if cmd.value is not None else 90.0
            self.state.yaw = (self.state.yaw + angle) % 360

# -------------------------------------------------
# Marker
# -------------------------------------------------
def make_marker(lat, lon, yaw):
    html = f"""
    <div style="
        transform: rotate({yaw}deg);
        font-size: 28px;
        color: #00e676;
        text-shadow: 1px 1px 3px black;
    ">➤</div>
    """
    icon = folium.DivIcon(html=html, icon_size=(36, 36), icon_anchor=(18, 18))
    return folium.Marker(location=[lat, lon], icon=icon, popup=f"Yaw: {yaw:.0f}° (0=North)")

# -------------------------------------------------
# Locations (chosen to be more open)
# -------------------------------------------------
LOCATIONS = {
    "Taipei 101 (open)": (25.0340, 121.5640),
    "NTU Campus": (25.0170, 121.5375),
    "Taipei Main Station": (25.0475, 121.5180),
    "Kaohsiung": (22.6275, 120.3015),
    "Bangalore MG Road": (12.9760, 77.6060),
    "Open Field": (25.0510, 121.5810),
}

# -------------------------------------------------
# App
# -------------------------------------------------
st.set_page_config(page_title="NaVILA-Lite", page_icon="🗺️", layout="wide")
st.title("🗺️ NaVILA-Lite (Clean Version)")
st.caption("Focus: Correct movement direction · Fast startup · Re-executable commands")

with st.sidebar:
    st.header("Controls")
    location_name = st.selectbox("Start Location", list(LOCATIONS.keys()))
    instruction = st.text_area(
        "Instruction",
        value="Move forward 100 meters then turn left 90 degrees then move 60 meters",
        height=90
    )
    c1, c2 = st.columns(2)
    exec_btn = c1.button("Execute", type="primary")
    reset_btn = c2.button("Reset")

# Session
if "ctrl" not in st.session_state:
    lat, lon = LOCATIONS["Taipei 101 (open)"]
    st.session_state.ctrl = MapController(lat, lon, yaw=0.0)
    st.session_state.planner = HybridPlanner()
    st.session_state.history = []
    st.session_state.loc = "Taipei 101 (open)"

ctrl = st.session_state.ctrl

if reset_btn or location_name != st.session_state.loc:
    lat, lon = LOCATIONS[location_name]
    ctrl.reset(lat, lon, yaw=0.0)
    st.session_state.history = []
    st.session_state.loc = location_name
    st.rerun()

if exec_btn and instruction.strip():
    cmds = st.session_state.planner.parse_multiple(instruction)
    for cmd in cmds:
        ctrl.execute(cmd)
        st.session_state.history.append(str(cmd))

# Map
m = folium.Map(location=[ctrl.state.lat, ctrl.state.lon], zoom_start=17)
folium.TileLayer("OpenStreetMap").add_to(m)
folium.TileLayer("CartoDB positron", name="Light").add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri", name="Satellite"
).add_to(m)

if len(ctrl.path) > 1:
    folium.PolyLine(ctrl.path, color="#1e90ff", weight=6, opacity=0.9).add_to(m)

folium.CircleMarker(ctrl.path[0], radius=7, color="lime", fill=True, fill_color="lime", popup="Start").add_to(m)
make_marker(ctrl.state.lat, ctrl.state.lon, ctrl.state.yaw).add_to(m)

folium.LayerControl().add_to(m)
st_folium(m, width=1000, height=600, key=f"m{len(ctrl.path)}")

# State
col1, col2 = st.columns(2)
with col1:
    st.subheader("Robot State")
    st.write(f"**Lat:** {ctrl.state.lat:.6f}")
    st.write(f"**Lon:** {ctrl.state.lon:.6f}")
    st.write(f"**Heading:** {ctrl.state.yaw:.1f}°  (0 = North)")

with col2:
    st.subheader("Commands")
    if st.session_state.history:
        for h in reversed(st.session_state.history[-8:]):
            st.code(h, language=None)
    else:
        st.info("No commands yet")

st.markdown("---")
st.caption("NaVILA-Lite Clean · Test movement direction first")
