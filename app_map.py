"""
NaVILA-Lite – Map-based Hierarchical Navigation
Final polish for submission

- Safe spawn (avoids starting inside buildings)
- Consistent heading + movement direction
- Multi-command support
- Optional real buildings (OSMnx)
- Re-executable commands
- Multiple map layers
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
import math
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple
import random

try:
    import osmnx as ox
    HAS_OSMNX = True
except ImportError:
    HAS_OSMNX = False

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
    yaw: float = 0.0  # 0 = North, increases clockwise (90 = East)

# -------------------------------------------------
# Planner
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
            return MidLevelCommand("turn_left", value if value is not None else 90.0, "heuristic")
        if any(w in text for w in self.right_words):
            return MidLevelCommand("turn_right", value if value is not None else 90.0, "heuristic")

        distance = value if value is not None else 30.0
        if "km" in text:
            distance = (value if value is not None else 1.0) * 1000.0
        return MidLevelCommand("move_forward", distance, "heuristic")

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
# Controller
# -------------------------------------------------
class MapController:
    def __init__(self, lat, lon, yaw=0.0):
        self.state = RobotState(lat, lon, yaw)
        self.path = [(lat, lon)]
        self.building_polys = []

    def reset(self, lat, lon, yaw=0.0):
        self.state = RobotState(lat, lon, yaw)
        self.path = [(lat, lon)]
        self.building_polys = []

    def load_buildings_around(self, lat, lon, dist=70):
        if not HAS_OSMNX:
            return False
        try:
            gdf = ox.features_from_point((lat, lon), tags={"building": True}, dist=dist)
            polys = []
            if gdf is not None and not gdf.empty:
                for geom in gdf.geometry:
                    if geom is None:
                        continue
                    if geom.geom_type == "Polygon":
                        polys.append(list(geom.exterior.coords))
                    elif geom.geom_type == "MultiPolygon":
                        for p in geom.geoms:
                            polys.append(list(p.exterior.coords))
            self.building_polys = polys[:40]
            return len(polys) > 0
        except Exception:
            return False

    def _point_in_poly(self, lat, lon, poly_coords):
        x, y = lon, lat
        inside = False
        n = len(poly_coords)
        j = n - 1
        for i in range(n):
            xi, yi = poly_coords[i][0], poly_coords[i][1]
            xj, yj = poly_coords[j][0], poly_coords[j][1]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
                inside = not inside
            j = i
        return inside

    def is_collision(self, lat, lon):
        for poly in self.building_polys:
            if self._point_in_poly(lat, lon, poly):
                return True
        return False

    def find_safe_spawn(self, lat, lon, max_tries=25):
        """Nudge start position if it is inside a building."""
        if not self.is_collision(lat, lon):
            return lat, lon
        for _ in range(max_tries):
            # small random offset (~15-40m)
            dlat = random.uniform(-0.00035, 0.00035)
            dlon = random.uniform(-0.00035, 0.00035)
            nlat, nlon = lat + dlat, lon + dlon
            if not self.is_collision(nlat, nlon):
                return nlat, nlon
        return lat, lon  # fallback

    def _move_step(self, distance_m: float):
        # yaw 0 = North, 90 = East
        rad = math.radians(self.state.yaw)
        d_north = distance_m * math.cos(rad)
        d_east  = distance_m * math.sin(rad)

        dlat = d_north / 111320.0
        dlon = d_east / (111320.0 * math.cos(math.radians(self.state.lat)) + 1e-8)

        new_lat = self.state.lat + dlat
        new_lon = self.state.lon + dlon

        if self.is_collision(new_lat, new_lon):
            for delta in [25, -25, 50, -50, 75, -75]:
                test_yaw = (self.state.yaw + delta) % 360
                rad_t = math.radians(test_yaw)
                dn = distance_m * math.cos(rad_t)
                de = distance_m * math.sin(rad_t)
                tlat = self.state.lat + dn / 111320.0
                tlon = self.state.lon + de / (111320.0 * math.cos(math.radians(self.state.lat)) + 1e-8)
                if not self.is_collision(tlat, tlon):
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
            dist = cmd.value if cmd.value is not None else 30.0
            step = 5.0
            steps = max(1, int(dist / step))
            actual = dist / steps
            for _ in range(steps):
                self._move_step(actual)
        elif cmd.action == "turn_left":
            angle = cmd.value if cmd.value is not None else 90.0
            self.state.yaw = (self.state.yaw - angle) % 360
        elif cmd.action == "turn_right":
            angle = cmd.value if cmd.value is not None else 90.0
            self.state.yaw = (self.state.yaw + angle) % 360

def create_heading_marker(lat, lon, yaw):
    # CSS rotation matches our yaw definition (0 = North)
    html = f"""
    <div style="
        transform: rotate({yaw}deg);
        font-size: 28px;
        color: #00e676;
        text-shadow: 1px 1px 3px #000;
    ">➤</div>
    """
    icon = folium.DivIcon(html=html, icon_size=(34, 34), icon_anchor=(17, 17))
    return folium.Marker([lat, lon], icon=icon, popup=f"Heading: {yaw:.1f}° (0=North)")

# -------------------------------------------------
# Locations (slightly safer)
# -------------------------------------------------
LOCATIONS = {
    "Taipei 101": (25.0339, 121.5640),
    "National Taiwan University": (25.0170, 121.5375),
    "Taipei Main Station": (25.0478, 121.5170),
    "Kaohsiung": (22.6275, 120.3010),
    "Tainan": (23.0005, 120.2270),
    "Bangalore MG Road": (12.9760, 77.6060),
    "Open Field": (25.0510, 121.5810),
}

# -------------------------------------------------
# App
# -------------------------------------------------
st.set_page_config(page_title="NaVILA-Lite", page_icon="🗺️", layout="wide")
st.title("🗺️ NaVILA-Lite – Map-based Hierarchical Navigation")
st.caption("Hierarchical language planner · Correct heading · Optional buildings · Multi-command")

with st.sidebar:
    st.header("Controls")
    location_name = st.selectbox("Start Location", list(LOCATIONS.keys()))
    load_buildings = st.checkbox("Load real buildings (OSMnx)", value=False,
                                 help="Optional. Turn on only when needed (can take time).")
    instruction = st.text_area(
        "Language Instruction(s)",
        value="Move forward 100 meters then turn left 90 degrees then move 60 meters",
        height=100
    )
    c1, c2 = st.columns(2)
    exec_btn = c1.button("Execute", type="primary")
    reset_btn = c2.button("Reset to Location")

if "controller" not in st.session_state:
    lat, lon = LOCATIONS["Taipei 101"]
    st.session_state.controller = MapController(lat, lon)
    st.session_state.planner = HybridPlanner()
    st.session_state.history = []
    st.session_state.current_location = "Taipei 101"

ctrl = st.session_state.controller

# Reset / location change
if reset_btn or location_name != st.session_state.current_location:
    lat, lon = LOCATIONS[location_name]
    ctrl.reset(lat, lon)
    st.session_state.history = []
    st.session_state.current_location = location_name

    if load_buildings and HAS_OSMNX:
        with st.spinner("Loading buildings + finding safe spawn..."):
            ctrl.load_buildings_around(lat, lon, dist=70)
            safe_lat, safe_lon = ctrl.find_safe_spawn(lat, lon)
            ctrl.reset(safe_lat, safe_lon)
    st.rerun()

# Load buildings on demand
if load_buildings and HAS_OSMNX and len(ctrl.building_polys) == 0:
    with st.spinner("Loading buildings + safe spawn..."):
        ctrl.load_buildings_around(ctrl.state.lat, ctrl.state.lon, dist=70)
        safe_lat, safe_lon = ctrl.find_safe_spawn(ctrl.state.lat, ctrl.state.lon)
        if (safe_lat, safe_lon) != (ctrl.state.lat, ctrl.state.lon):
            ctrl.reset(safe_lat, safe_lon)
            st.sidebar.success("Moved to safe spawn point")

# Execute (always append, allows re-execution)
if exec_btn and instruction.strip():
    cmds = st.session_state.planner.parse_multiple(instruction)
    for cmd in cmds:
        ctrl.execute(cmd)
        st.session_state.history.append({"command": str(cmd), "source": cmd.source})

# Map
m = folium.Map(location=[ctrl.state.lat, ctrl.state.lon], zoom_start=17)
folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
folium.TileLayer("CartoDB positron", name="Light").add_to(m)
folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri", name="Satellite"
).add_to(m)

if len(ctrl.path) > 1:
    folium.PolyLine(ctrl.path, color="#1e90ff", weight=6, opacity=0.9).add_to(m)

for poly in ctrl.building_polys:
    try:
        locs = [(lat, lon) for lon, lat in poly]
        folium.Polygon(locs, color="#c0392b", weight=1, fill=True, fill_opacity=0.3).add_to(m)
    except Exception:
        pass

if ctrl.path:
    folium.CircleMarker(ctrl.path[0], radius=7, color="lime", fill=True, fill_color="lime", popup="Start").add_to(m)

create_heading_marker(ctrl.state.lat, ctrl.state.lon, ctrl.state.yaw).add_to(m)
folium.LayerControl(collapsed=False).add_to(m)

st_folium(m, width=1000, height=620, key=f"map_{len(ctrl.path)}_{st.session_state.current_location}")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Robot State")
    st.metric("Latitude", f"{ctrl.state.lat:.6f}")
    st.metric("Longitude", f"{ctrl.state.lon:.6f}")
    st.metric("Heading (0=North)", f"{ctrl.state.yaw:.1f}°")
    st.write(f"Buildings: **{len(ctrl.building_polys)}**")

with col2:
    st.subheader("Executed Commands")
    if st.session_state.history:
        for h in reversed(st.session_state.history[-10:]):
            st.markdown(f"`{h['command']}` <span style='color:gray;font-size:0.85em'>({h['source']})</span>", unsafe_allow_html=True)
    else:
        st.info("No commands yet")

st.markdown("---")
st.markdown("""
**Honest Limitations**
- This is a hierarchical NaVILA-style demo (High-level language → mid-level commands → low-level movement).
- Building collision is simple geometric (not semantic road following).
- Real VLM/VLA weights are optional/heavy; current planner is hybrid heuristic + ready for VLM plug-in.
- Full Street View or Isaac Sim level simulation is out of scope on free hardware.
""")
st.caption("NaVILA-Lite · Ready for demonstration · Inspired by NaVILA (RSS 2025)")
