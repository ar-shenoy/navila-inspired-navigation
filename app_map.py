"""
NaVILA-Lite – Final version for submission

Fixes:
- Clearer robot marker
- Dynamic building loading while moving
- Support for return / go back commands
- Hybrid planner (heuristic + VLM-ready structure)
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
        if self.action == "return_home":
            return "return to start"
        if self.value is not None:
            if "turn" in self.action:
                return f"{self.action.replace('_', ' ')} {self.value:.0f}°"
            return f"{self.action.replace('_', ' ')} {self.value:.1f}m"
        return self.action.replace("_", " ")

@dataclass
class RobotState:
    lat: float
    lon: float
    yaw: float = 0.0  # 0 = North, 90 = East

# -------------------------------------------------
# Hybrid Planner
# -------------------------------------------------
class HybridPlanner:
    def __init__(self):
        self.forward_words = ["forward", "ahead", "straight", "go", "move", "walk", "advance"]
        self.left_words = ["left"]
        self.right_words = ["right"]
        self.stop_words = ["stop", "halt", "wait", "stay"]
        self.return_words = ["return", "back", "home", "original", "start"]

    def _parse_single(self, text: str) -> MidLevelCommand:
        text = text.lower().strip()

        if any(w in text for w in self.return_words):
            return MidLevelCommand("return_home", source="heuristic")

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
            if any(w in p for w in self.forward_words + self.left_words + self.right_words + self.stop_words + self.return_words):
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
        self.start_lat = lat
        self.start_lon = lon
        self.path = [(lat, lon)]
        self.building_polys = []
        self.last_building_center = (lat, lon)

    def reset(self, lat, lon, yaw=0.0):
        self.state = RobotState(lat, lon, yaw)
        self.start_lat = lat
        self.start_lon = lon
        self.path = [(lat, lon)]
        self.building_polys = []
        self.last_building_center = (lat, lon)

    def load_buildings_around(self, lat, lon, dist=90):
        if not HAS_OSMNX:
            return False
        try:
            gdf = ox.features_from_point((lat, lon), tags={"building": True}, dist=dist)
            polys = []
            if gdf is not None and not gdf.empty:
                for geom in gdf.geometry:
                    if geom is None: continue
                    if geom.geom_type == "Polygon":
                        polys.append(list(geom.exterior.coords))
                    elif geom.geom_type == "MultiPolygon":
                        for p in geom.geoms:
                            polys.append(list(p.exterior.coords))
            # Keep recent ones + new ones
            self.building_polys = (self.building_polys + polys)[-55:]
            self.last_building_center = (lat, lon)
            return len(polys) > 0
        except Exception:
            return False

    def maybe_reload_buildings(self, threshold_m=90):
        dist = self._distance_m(self.state.lat, self.state.lon,
                                self.last_building_center[0], self.last_building_center[1])
        if dist > threshold_m and HAS_OSMNX:
            self.load_buildings_around(self.state.lat, self.state.lon, dist=90)

    def _distance_m(self, lat1, lon1, lat2, lon2):
        R = 6371000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

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

    def find_safe_spawn(self, lat, lon, max_tries=30):
        if not self.is_collision(lat, lon):
            return lat, lon
        for _ in range(max_tries):
            dlat = random.uniform(-0.0004, 0.0004)
            dlon = random.uniform(-0.0004, 0.0004)
            nlat, nlon = lat + dlat, lon + dlon
            if not self.is_collision(nlat, nlon):
                return nlat, nlon
        return lat, lon

    def _move_step(self, distance_m: float):
        rad = math.radians(self.state.yaw)
        d_north = distance_m * math.cos(rad)
        d_east  = distance_m * math.sin(rad)

        dlat = d_north / 111320.0
        dlon = d_east / (111320.0 * math.cos(math.radians(self.state.lat)) + 1e-8)

        new_lat = self.state.lat + dlat
        new_lon = self.state.lon + dlon

        if self.is_collision(new_lat, new_lon):
            for delta in [20, -20, 40, -40, 60, -60, 90, -90]:
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

        if cmd.action == "return_home":
            # Simple return: face toward start and move
            dlat = self.start_lat - self.state.lat
            dlon = self.start_lon - self.state.lon
            target_yaw = (math.degrees(math.atan2(dlon, dlat)) + 360) % 360
            self.state.yaw = target_yaw
            dist = self._distance_m(self.state.lat, self.state.lon, self.start_lat, self.start_lon)
            step = 8.0
            steps = max(1, int(dist / step))
            actual = dist / steps
            for _ in range(steps):
                self._move_step(actual)
                self.maybe_reload_buildings()
            return

        if cmd.action == "move_forward":
            dist = cmd.value if cmd.value is not None else 30.0
            step = 6.0
            steps = max(1, int(dist / step))
            actual = dist / steps
            for _ in range(steps):
                self._move_step(actual)
                self.maybe_reload_buildings()

        elif cmd.action == "turn_left":
            angle = cmd.value if cmd.value is not None else 90.0
            self.state.yaw = (self.state.yaw - angle) % 360

        elif cmd.action == "turn_right":
            angle = cmd.value if cmd.value is not None else 90.0
            self.state.yaw = (self.state.yaw + angle) % 360

def create_robot_marker(lat, lon, yaw):
    """Clearer robot marker."""
    html = f"""
    <div style="
        transform: rotate({yaw}deg);
        font-size: 26px;
        color: #00e676;
        text-shadow: 1px 1px 3px #000;
        background: rgba(0,0,0,0.35);
        border-radius: 50%;
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
    ">▲</div>
    """
    icon = folium.DivIcon(html=html, icon_size=(32, 32), icon_anchor=(16, 16))
    return folium.Marker([lat, lon], icon=icon, popup=f"Robot | Heading: {yaw:.0f}° (0=North)")

# -------------------------------------------------
# Locations
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
st.caption("Hierarchical planner · Dynamic buildings · Return command · Hybrid (heuristic + VLM-ready)")

with st.sidebar:
    st.header("Controls")
    location_name = st.selectbox("Start Location", list(LOCATIONS.keys()))
    load_buildings = st.checkbox("Load real buildings (OSMnx)", value=False,
                                 help="Optional. Enables dynamic building obstacles.")
    instruction = st.text_area(
        "Language Instruction(s)",
        value="Move forward 80 meters then turn left 90 degrees then move 50 meters",
        height=100,
        help="Supports: move, turn left/right, stop, return / go back"
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

if reset_btn or location_name != st.session_state.current_location:
    lat, lon = LOCATIONS[location_name]
    ctrl.reset(lat, lon)
    st.session_state.history = []
    st.session_state.current_location = location_name
    if load_buildings and HAS_OSMNX:
        with st.spinner("Loading buildings + safe spawn..."):
            ctrl.load_buildings_around(lat, lon, dist=90)
            safe_lat, safe_lon = ctrl.find_safe_spawn(lat, lon)
            ctrl.reset(safe_lat, safe_lon)
    st.rerun()

if load_buildings and HAS_OSMNX and len(ctrl.building_polys) == 0:
    with st.spinner("Loading buildings..."):
        ctrl.load_buildings_around(ctrl.state.lat, ctrl.state.lon, dist=90)
        safe_lat, safe_lon = ctrl.find_safe_spawn(ctrl.state.lat, ctrl.state.lon)
        if (safe_lat, safe_lon) != (ctrl.state.lat, ctrl.state.lon):
            ctrl.reset(safe_lat, safe_lon)
            st.sidebar.success("Safe spawn applied")

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
        folium.Polygon(locs, color="#c0392b", weight=1, fill=True, fill_opacity=0.28).add_to(m)
    except Exception:
        pass

if ctrl.path:
    folium.CircleMarker(ctrl.path[0], radius=7, color="lime", fill=True, fill_color="lime", popup="Start").add_to(m)

create_robot_marker(ctrl.state.lat, ctrl.state.lon, ctrl.state.yaw).add_to(m)
folium.LayerControl(collapsed=False).add_to(m)

st_folium(m, width=1000, height=620, key=f"map_{len(ctrl.path)}")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Robot State")
    st.metric("Latitude", f"{ctrl.state.lat:.6f}")
    st.metric("Longitude", f"{ctrl.state.lon:.6f}")
    st.metric("Heading (0=North)", f"{ctrl.state.yaw:.1f}°")
    st.write(f"Buildings in memory: **{len(ctrl.building_polys)}**")

with col2:
    st.subheader("Executed Commands")
    if st.session_state.history:
        for h in reversed(st.session_state.history[-10:]):
            st.markdown(f"`{h['command']}` <span style='color:gray;font-size:0.85em'>({h['source']})</span>", unsafe_allow_html=True)
    else:
        st.info("No commands yet")

st.markdown("---")
st.markdown("""
**Project Notes (for submission)**
- Architecture follows NaVILA hierarchical design: High-level language → mid-level commands → low-level execution.
- Planner is hybrid (strong heuristic + structure ready for lightweight VLM).
- Buildings are loaded dynamically as the robot moves (when enabled).
- "Return / go back" command is supported.
- Limitations: geometric collision only, not full semantic road following or trained VLA weights.
""")
st.caption("NaVILA-Lite · Hierarchical navigation demo · Inspired by NaVILA (RSS 2025)")
