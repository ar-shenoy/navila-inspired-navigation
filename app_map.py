"""
NaVILA-Lite – Map-based Hierarchical Navigation
Restored full features + fixed heading math

Features:
- Hierarchical high-level planner (multi-command + long distance)
- Correct heading → movement direction
- Multiple map layers
- Optional real building obstacles via OSMnx (lightweight)
- Re-executable commands
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
import math
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple

try:
    import osmnx as ox
    HAS_OSMNX = True
except ImportError:
    HAS_OSMNX = False

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
    yaw: float = 0.0  # 0 = North, 90 = East, 180 = South, 270 = West

# -------------------------------------------------
# Hierarchical Planner (multi-command)
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
            angle = value if value is not None else 90.0
            return MidLevelCommand("turn_left", angle, "heuristic")

        if any(w in text for w in self.right_words):
            angle = value if value is not None else 90.0
            return MidLevelCommand("turn_right", angle, "heuristic")

        distance = value if value is not None else 30.0
        if "km" in text:
            distance = (value if value is not None else 1.0) * 1000.0

        return MidLevelCommand("move_forward", distance, "heuristic")

    def parse_multiple(self, instruction: str) -> List[MidLevelCommand]:
        parts = re.split(r",| and | then |\.", instruction.lower())
        parts = [p.strip() for p in parts if p.strip()]

        commands = []
        for part in parts:
            if any(w in part for w in self.forward_words + self.left_words + self.right_words + self.stop_words):
                commands.append(self._parse_single(part))

        if not commands:
            commands.append(self._parse_single(instruction))
        return commands

# -------------------------------------------------
# Controller with FIXED heading math
# -------------------------------------------------
class MapController:
    def __init__(self, lat, lon, yaw=0.0):
        self.state = RobotState(lat=lat, lon=lon, yaw=yaw)
        self.path: List[Tuple[float, float]] = [(lat, lon)]
        self.building_polys = []
        self.last_building_center = (lat, lon)

    def reset(self, lat, lon, yaw=0.0):
        self.state = RobotState(lat=lat, lon=lon, yaw=yaw)
        self.path = [(lat, lon)]
        self.building_polys = []
        self.last_building_center = (lat, lon)

    def load_buildings_around(self, lat, lon, dist=80):
        """Lightweight building load."""
        if not HAS_OSMNX:
            return False
        try:
            tags = {"building": True}
            gdf = ox.features_from_point((lat, lon), tags=tags, dist=dist)
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
            self.building_polys = polys[:50]  # hard limit for speed
            self.last_building_center = (lat, lon)
            return len(polys) > 0
        except Exception:
            return False

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

    def _is_collision(self, lat, lon):
        for poly in self.building_polys:
            if self._point_in_poly(lat, lon, poly):
                return True
        return False

    def _move_step(self, distance_m: float):
        """
        FIXED MATH:
        yaw = 0   → North
        yaw = 90  → East
        yaw = 180 → South
        yaw = 270 → West
        """
        rad = math.radians(self.state.yaw)
        d_north = distance_m * math.cos(rad)
        d_east  = distance_m * math.sin(rad)

        dlat = d_north / 111320.0
        dlon = d_east / (111320.0 * math.cos(math.radians(self.state.lat)) + 1e-8)

        new_lat = self.state.lat + dlat
        new_lon = self.state.lon + dlon

        # Simple avoidance
        if self._is_collision(new_lat, new_lon):
            for delta in [20, -20, 40, -40, 60, -60]:
                test_yaw = (self.state.yaw + delta) % 360
                rad_t = math.radians(test_yaw)
                dn = distance_m * math.cos(rad_t)
                de = distance_m * math.sin(rad_t)
                tlat = self.state.lat + dn / 111320.0
                tlon = self.state.lon + de / (111320.0 * math.cos(math.radians(self.state.lat)) + 1e-8)
                if not self._is_collision(tlat, tlon):
                    self.state.yaw = test_yaw
                    self.state.lat = tlat
                    self.state.lon = tlon
                    self.path.append((tlat, tlon))
                    return
            return  # stuck

        self.state.lat = new_lat
        self.state.lon = new_lon
        self.path.append((new_lat, new_lon))

    def execute(self, cmd: MidLevelCommand):
        if cmd.action == "stop":
            return

        if cmd.action == "move_forward":
            dist = cmd.value if cmd.value is not None else 30.0
            step = 6.0
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
# Locations
# -------------------------------------------------
LOCATIONS = {
    "Taipei 101": (25.0338, 121.5642),
    "National Taiwan University": (25.0172, 121.5378),
    "Taipei Main Station": (25.0472, 121.5178),
    "Kaohsiung": (22.6276, 120.3012),
    "Tainan": (23.0003, 120.2272),
    "Bangalore MG Road": (12.9758, 77.6062),
    "Open Field": (25.0508, 121.5808),
}

# -------------------------------------------------
# Streamlit App
# -------------------------------------------------
st.set_page_config(page_title="NaVILA-Lite", page_icon="🗺️", layout="wide")

st.title("🗺️ NaVILA-Lite – Map-based Hierarchical Navigation")
st.caption("Hierarchical planner · Correct heading math · Optional real buildings · Multi-command support")

with st.sidebar:
    st.header("Controls")
    location_name = st.selectbox("Start Location", list(LOCATIONS.keys()))
    
    load_buildings = st.checkbox(
        "Load real buildings (OSMnx)",
        value=False,
        help="Optional. Can take 15-40 seconds the first time."
    )

    instruction = st.text_area(
        "Language Instruction(s)",
        value="Move forward 120 meters then turn left 90 degrees then move 80 meters",
        height=100,
        help="Supports multiple commands: move ... then turn ... then move ..."
    )

    col1, col2 = st.columns(2)
    execute_btn = col1.button("Execute", type="primary")
    reset_btn = col2.button("Reset to Location")

# Session state
if "controller" not in st.session_state:
    lat, lon = LOCATIONS["Taipei 101"]
    st.session_state.controller = MapController(lat, lon, yaw=0.0)
    st.session_state.planner = HybridPlanner()
    st.session_state.history = []
    st.session_state.current_location = "Taipei 101"

ctrl = st.session_state.controller

# Location change / Reset
if reset_btn or location_name != st.session_state.current_location:
    lat, lon = LOCATIONS[location_name]
    ctrl.reset(lat, lon, yaw=0.0)
    st.session_state.history = []
    st.session_state.current_location = location_name
    st.rerun()

# Optional building load (only when checked)
if load_buildings and HAS_OSMNX and len(ctrl.building_polys) == 0:
    with st.spinner("Loading buildings (lightweight)..."):
        ok = ctrl.load_buildings_around(ctrl.state.lat, ctrl.state.lon, dist=80)
        if ok:
            st.sidebar.success(f"Loaded {len(ctrl.building_polys)} buildings")
        else:
            st.sidebar.warning("No buildings found / failed")

elif not HAS_OSMNX:
    st.sidebar.info("OSMnx not installed – buildings disabled")

# Execute commands (re-executable)
if execute_btn and instruction.strip():
    commands = st.session_state.planner.parse_multiple(instruction)
    for cmd in commands:
        ctrl.execute(cmd)
        st.session_state.history.append({
            "command": str(cmd),
            "source": cmd.source
        })

# -------------------- Map --------------------
m = folium.Map(location=[ctrl.state.lat, ctrl.state.lon], zoom_start=17)

# Multiple layers
folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
folium.TileLayer("CartoDB positron", name="Light").add_to(m)
folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)
folium.TileLayer(
    tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    attr="OpenTopoMap", name="Topo"
).add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri", name="Satellite"
).add_to(m)

# Path
if len(ctrl.path) > 1:
    folium.PolyLine(ctrl.path, color="#1e90ff", weight=6, opacity=0.9).add_to(m)

# Buildings
for poly in ctrl.building_polys:
    try:
        locations = [(lat, lon) for lon, lat in poly]
        folium.Polygon(locations, color="#c0392b", weight=1, fill=True, fill_opacity=0.3).add_to(m)
    except Exception:
        pass

# Start + Robot
if ctrl.path:
    folium.CircleMarker(ctrl.path[0], radius=7, color="lime", fill=True, fill_color="lime", popup="Start").add_to(m)

create_heading_marker(ctrl.state.lat, ctrl.state.lon, ctrl.state.yaw).add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

st_folium(m, width=1000, height=620, key=f"map_{len(ctrl.path)}_{st.session_state.current_location}")

# Info panels
col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Robot State")
    st.metric("Latitude", f"{ctrl.state.lat:.6f}")
    st.metric("Longitude", f"{ctrl.state.lon:.6f}")
    st.metric("Heading (0=North)", f"{ctrl.state.yaw:.1f}°")
    st.write(f"Buildings loaded: **{len(ctrl.building_polys)}**")

with col_b:
    st.subheader("Executed Commands")
    if st.session_state.history:
        for h in reversed(st.session_state.history[-10:]):
            st.markdown(
                f"`{h['command']}`  <span style='color:gray;font-size:0.85em'>({h['source']})</span>",
                unsafe_allow_html=True
            )
    else:
        st.info("No commands yet")

st.markdown("---")
st.markdown("""
**Limitations (honest)**  
- Building loading is optional and limited for performance  
- Collision avoidance is simple reactive (not full path planning)  
- This is a hierarchical VLA-style demo, not a full trained NaVILA model  
- Real Street View / Isaac Sim level simulation is out of scope for free hardware
""")
st.caption("NaVILA-Lite · Hierarchical navigation on real maps · Inspired by NaVILA (RSS 2025)")
