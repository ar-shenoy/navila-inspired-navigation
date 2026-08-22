"""
NaVILA-Lite – Map-based Hierarchical Navigation
Critical fixes version:
- Correct heading → movement direction
- Safer start positions (open space)
- Better collision handling
- Commands can be re-executed
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
    yaw: float = 0.0   # 0 = North, 90 = East, 180 = South, 270 = West


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
            angle = value if value is not None else 30.0
            return MidLevelCommand("turn_left", angle, "heuristic")

        if any(w in text for w in self.right_words):
            angle = value if value is not None else 30.0
            return MidLevelCommand("turn_right", angle, "heuristic")

        distance = value if value is not None else 20.0
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
# Controller – FIXED movement math
# -------------------------------------------------
class MapController:
    def __init__(self, start_lat, start_lon, yaw=0.0):
        self.state = RobotState(lat=start_lat, lon=start_lon, yaw=yaw)
        self.path: List[Tuple[float, float]] = [(start_lat, start_lon)]
        self.obstacles: List[Tuple[float, float, float]] = []
        self.building_polys = []
        self.last_building_center = (start_lat, start_lon)

    def reset(self, lat, lon, yaw=0.0):
        self.state = RobotState(lat=lat, lon=lon, yaw=yaw)
        self.path = [(lat, lon)]
        self.building_polys = []
        self.obstacles = []
        self.last_building_center = (lat, lon)

    def set_obstacles(self, obstacles):
        self.obstacles = obstacles

    def load_buildings_around(self, lat, lon, dist=150):
        if not HAS_OSMNX:
            return False
        try:
            tags = {"building": True}
            gdf = ox.features_from_point((lat, lon), tags=tags, dist=dist)
            new_polys = []
            if gdf is not None and not gdf.empty:
                for geom in gdf.geometry:
                    if geom is None:
                        continue
                    if geom.geom_type == "Polygon":
                        new_polys.append(list(geom.exterior.coords))
                    elif geom.geom_type == "MultiPolygon":
                        for poly in geom.geoms:
                            new_polys.append(list(poly.exterior.coords))
            self.building_polys.extend(new_polys)
            if len(self.building_polys) > 100:
                self.building_polys = self.building_polys[-100:]
            self.last_building_center = (lat, lon)
            return len(new_polys) > 0
        except Exception as e:
            return False

    def maybe_reload_buildings(self, threshold_m=130):
        if not HAS_OSMNX:
            return
        dist = self._distance_m(self.state.lat, self.state.lon,
                                self.last_building_center[0], self.last_building_center[1])
        if dist > threshold_m:
            self.load_buildings_around(self.state.lat, self.state.lon, dist=150)

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

    def _is_collision(self, lat, lon, robot_radius=3.5):
        for olat, olon, radius in self.obstacles:
            if self._distance_m(lat, lon, olat, olon) < (radius + robot_radius):
                return True
        for poly in self.building_polys:
            if self._point_in_poly(lat, lon, poly):
                return True
        return False

    def _move_step(self, distance_m: float):
        """
        FIXED: yaw = 0 means North.
        Increasing yaw turns clockwise (right).
        """
        # Convert yaw to math angle (0 North → standard math 90°)
        rad = math.radians(self.state.yaw)

        # North component (lat) and East component (lon)
        d_north = distance_m * math.cos(rad)
        d_east  = distance_m * math.sin(rad)

        dlat = d_north / 111320.0
        dlon = d_east / (111320.0 * math.cos(math.radians(self.state.lat)) + 1e-8)

        new_lat = self.state.lat + dlat
        new_lon = self.state.lon + dlon

        if self._is_collision(new_lat, new_lon):
            # Try small turns to avoid
            for delta in [15, -15, 30, -30, 45, -45, 60, -60]:
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
            # Could not move
            return

        self.state.lat = new_lat
        self.state.lon = new_lon
        self.path.append((new_lat, new_lon))

    def execute(self, cmd: MidLevelCommand):
        if cmd.action == "stop":
            return

        if cmd.action == "move_forward":
            dist = cmd.value if cmd.value is not None else 20.0
            step_size = 5.0
            steps = max(1, int(dist / step_size))
            actual_step = dist / steps
            for _ in range(steps):
                self._move_step(actual_step)
                self.maybe_reload_buildings()

        elif cmd.action == "turn_left":
            # Left = decrease yaw (counter-clockwise)
            angle = cmd.value if cmd.value is not None else 30.0
            self.state.yaw = (self.state.yaw - angle) % 360

        elif cmd.action == "turn_right":
            # Right = increase yaw (clockwise)
            angle = cmd.value if cmd.value is not None else 30.0
            self.state.yaw = (self.state.yaw + angle) % 360


def create_heading_marker(lat, lon, yaw):
    # Arrow points in the direction of yaw (0 = North)
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
# Safer start positions (open areas)
# -------------------------------------------------
LOCATIONS = {
    # Slightly offset to open roads / plazas
    "Taipei 101": (25.0336, 121.5645),
    "National Taiwan University": (25.0175, 121.5380),
    "Taipei Main Station": (25.0468, 121.5175),
    "Kaohsiung": (22.6278, 120.3010),
    "Tainan": (23.0005, 120.2275),
    "Bangalore MG Road": (12.9755, 77.6065),
    "Open Field (Test)": (25.0505, 121.5805),
}

# -------------------------------------------------
# Streamlit App
# -------------------------------------------------
st.set_page_config(page_title="NaVILA-Lite", page_icon="🗺️", layout="wide")

st.title("🗺️ NaVILA-Lite – Map-based Hierarchical Navigation")
st.caption("High-level language → Mid-level commands → Movement + reactive avoidance")

with st.sidebar:
    st.header("Controls")
    location_name = st.selectbox("Start Location", list(LOCATIONS.keys()))
    load_buildings = st.checkbox("Load real buildings (OSMnx)", value=True)

    instruction = st.text_area(
        "Language Instruction(s)",
        value="Move forward 100 meters then turn left 90 degrees then move 60 meters",
        height=100
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

# Reset / location change
if reset_btn or (location_name != st.session_state.current_location):
    lat, lon = LOCATIONS[location_name]
    ctrl.reset(lat, lon, yaw=0.0)
    st.session_state.history = []
    st.session_state.current_location = location_name
    if load_buildings and HAS_OSMNX:
        with st.spinner("Loading buildings..."):
            ctrl.load_buildings_around(lat, lon, dist=140)
    st.rerun()

if load_buildings and HAS_OSMNX and len(ctrl.building_polys) == 0:
    with st.spinner("Loading buildings..."):
        ctrl.load_buildings_around(ctrl.state.lat, ctrl.state.lon, dist=140)

if not HAS_OSMNX:
    st.sidebar.warning("OSMnx not installed")

# Execute (always allow re-execution)
if execute_btn and instruction.strip():
    commands = st.session_state.planner.parse_multiple(instruction)
    for cmd in commands:
        ctrl.execute(cmd)
        st.session_state.history.append({
            "command": str(cmd),
            "source": cmd.source
        })

# Fallback artificial obstacles only if no buildings
if len(ctrl.building_polys) == 0:
    ctrl.set_obstacles([])

# -------------------- Map --------------------
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

for poly in ctrl.building_polys[-80:]:
    try:
        locations = [(lat, lon) for lon, lat in poly]
        folium.Polygon(locations, color="#c0392b", weight=1, fill=True, fill_opacity=0.25).add_to(m)
    except Exception:
        pass

if ctrl.path:
    folium.CircleMarker(ctrl.path[0], radius=7, color="lime", fill=True, fill_color="lime", popup="Start").add_to(m)

create_heading_marker(ctrl.state.lat, ctrl.state.lon, ctrl.state.yaw).add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

st_folium(m, width=1000, height=620, key=f"map_{st.session_state.current_location}")

# Info
col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Robot State")
    st.metric("Latitude", f"{ctrl.state.lat:.6f}")
    st.metric("Longitude", f"{ctrl.state.lon:.6f}")
    st.metric("Heading (0=North)", f"{ctrl.state.yaw:.1f}°")
    st.write(f"Buildings in memory: **{len(ctrl.building_polys)}**")

with col_b:
    st.subheader("Executed Commands")
    if st.session_state.history:
        for h in reversed(st.session_state.history[-12:]):
            st.markdown(
                f"`{h['command']}`  <span style='color:gray;font-size:0.85em'>({h['source']})</span>",
                unsafe_allow_html=True
            )
    else:
        st.info("No commands yet. Type an instruction and press Execute.")

st.markdown("---")
st.caption("NaVILA-Lite · Hierarchical navigation demo · Inspired by NaVILA (RSS 2025)")
