"""
NaVILA-Lite – Map-based Hierarchical Navigation (Improved)

- Multi-command language instructions
- Long distance support
- Hybrid high-level planner
- Real building obstacles via OSMnx (with fallback)
- Better robot heading visualization
- Basic reactive obstacle avoidance
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
import math
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple
import numpy as np

# Optional OSMnx for real buildings
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
    yaw: float = 0.0  # degrees, 0 = North, increases clockwise? we use math convention carefully


# -------------------------------------------------
# Hybrid Planner (multi-command)
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
# Map Controller with real / fallback obstacles
# -------------------------------------------------
class MapController:
    def __init__(self, start_lat=25.0330, start_lon=121.5654):
        self.state = RobotState(lat=start_lat, lon=start_lon, yaw=0.0)
        self.path: List[Tuple[float, float]] = [(start_lat, start_lon)]
        self.obstacles: List[Tuple[float, float, float]] = []  # lat, lon, radius_m
        self.building_polys = []  # optional list of polygons

    def reset(self, lat, lon, yaw=0.0):
        self.state = RobotState(lat=lat, lon=lon, yaw=yaw)
        self.path = [(lat, lon)]
        self.building_polys = []

    def set_obstacles(self, obstacles):
        self.obstacles = obstacles

    def load_buildings_around(self, lat, lon, dist=120):
        """Try to load real buildings with OSMnx. Fallback to empty."""
        self.building_polys = []
        if not HAS_OSMNX:
            return False
        try:
            # Download buildings around point
            tags = {"building": True}
            gdf = ox.features_from_point((lat, lon), tags=tags, dist=dist)
            if gdf is not None and not gdf.empty:
                for geom in gdf.geometry:
                    if geom is None:
                        continue
                    if geom.geom_type == "Polygon":
                        coords = list(geom.exterior.coords)
                        self.building_polys.append(coords)
                    elif geom.geom_type == "MultiPolygon":
                        for poly in geom.geoms:
                            coords = list(poly.exterior.coords)
                            self.building_polys.append(coords)
            return len(self.building_polys) > 0
        except Exception as e:
            st.warning(f"Could not load real buildings: {e}")
            return False

    def _distance_m(self, lat1, lon1, lat2, lon2):
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def _point_in_poly(self, lat, lon, poly_coords):
        """Simple ray casting for point in polygon (lon, lat order)."""
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

    def _is_collision(self, lat, lon, robot_radius=4.0):
        # Check circular obstacles
        for olat, olon, radius in self.obstacles:
            if self._distance_m(lat, lon, olat, olon) < (radius + robot_radius):
                return True
        # Check real building polygons
        for poly in self.building_polys:
            if self._point_in_poly(lat, lon, poly):
                return True
        return False

    def _move_step(self, distance_m: float):
        # yaw: 0 = East in standard math? We define 0 = North for map intuition
        # Convert: math angle = 90 - yaw
        math_angle = math.radians(90.0 - self.state.yaw)

        dy = distance_m * math.sin(math_angle)   # North component
        dx = distance_m * math.cos(math_angle)   # East component

        dlat = dy / 111320.0
        dlon = dx / (111320.0 * math.cos(math.radians(self.state.lat)) + 1e-8)

        new_lat = self.state.lat + dlat
        new_lon = self.state.lon + dlon

        if self._is_collision(new_lat, new_lon):
            # Reactive avoidance
            for delta in [20, -20, 40, -40, 60, -60, 90, -90]:
                test_yaw = (self.state.yaw + delta) % 360
                math_a = math.radians(90.0 - test_yaw)
                dy2 = distance_m * math.sin(math_a)
                dx2 = distance_m * math.cos(math_a)
                tlat = self.state.lat + dy2 / 111320.0
                tlon = self.state.lon + dx2 / (111320.0 * math.cos(math.radians(self.state.lat)) + 1e-8)
                if not self._is_collision(tlat, tlon):
                    self.state.yaw = test_yaw
                    self.state.lat = tlat
                    self.state.lon = tlon
                    self.path.append((tlat, tlon))
                    return
            return  # completely stuck

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

        elif cmd.action == "turn_left":
            angle = cmd.value if cmd.value is not None else 30.0
            self.state.yaw = (self.state.yaw - angle) % 360   # left = counter-clockwise on map

        elif cmd.action == "turn_right":
            angle = cmd.value if cmd.value is not None else 30.0
            self.state.yaw = (self.state.yaw + angle) % 360


# -------------------------------------------------
# Helper: create rotated marker for heading
# -------------------------------------------------
def create_heading_marker(lat, lon, yaw):
    """Create a simple DivIcon arrow that roughly shows heading."""
    # CSS rotation
    rotation = yaw  # adjust if needed
    html = f"""
    <div style="
        transform: rotate({rotation}deg);
        font-size: 24px;
        color: #00cc44;
        text-shadow: 1px 1px 2px black;
    ">➤</div>
    """
    icon = folium.DivIcon(
        html=html,
        icon_size=(30, 30),
        icon_anchor=(15, 15),
    )
    return folium.Marker([lat, lon], icon=icon, popup=f"Yaw: {yaw:.1f}°")


# -------------------------------------------------
# Streamlit App
# -------------------------------------------------
st.set_page_config(page_title="NaVILA-Lite Map Navigation", page_icon="🗺️", layout="wide")

st.title("🗺️ NaVILA-Lite – Map-based Hierarchical Navigation")
st.markdown("""
**NaVILA-style hierarchical navigation on real maps**  
High-level language → Mid-level commands → Movement + reactive obstacle avoidance  
(Real buildings loaded via OSMnx when available)
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
    load_buildings = st.checkbox("Load real buildings (OSMnx)", value=True,
                                 help="Downloads building footprints around the start point. May take a few seconds.")
    instruction = st.text_area(
        "Language Instruction(s)",
        value="Move forward 120 meters then turn left 90 degrees then move 80 meters",
        height=110,
        help="Example: move 200m then turn left 90 then move 150m"
    )
    col1, col2 = st.columns(2)
    execute_btn = col1.button("Execute", type="primary")
    reset_btn = col2.button("Reset")

if "controller" not in st.session_state:
    lat, lon = LOCATIONS["Taipei 101"]
    st.session_state.controller = MapController(lat, lon)
    st.session_state.planner = HybridPlanner()
    st.session_state.history = []
    st.session_state.buildings_loaded = False

if reset_btn:
    lat, lon = LOCATIONS[location_name]
    st.session_state.controller.reset(lat, lon)
    st.session_state.history = []
    st.session_state.buildings_loaded = False
    st.rerun()

ctrl = st.session_state.controller

# Load buildings on demand
if load_buildings and not st.session_state.buildings_loaded and HAS_OSMNX:
    with st.spinner("Loading real buildings from OpenStreetMap..."):
        success = ctrl.load_buildings_around(ctrl.state.lat, ctrl.state.lon, dist=150)
        st.session_state.buildings_loaded = True
        if success:
            st.sidebar.success(f"Loaded {len(ctrl.building_polys)} buildings")
        else:
            st.sidebar.info("No buildings loaded – using fallback")

elif not HAS_OSMNX:
    st.sidebar.warning("OSMnx not installed. Install with: pip install osmnx")

if execute_btn and instruction.strip():
    commands = st.session_state.planner.parse_multiple(instruction)
    for cmd in commands:
        ctrl.execute(cmd)
        st.session_state.history.append({
            "command": str(cmd),
            "source": cmd.source
        })

# Fallback artificial obstacles if no buildings
if len(ctrl.building_polys) == 0 and location_name == "Taipei 101":
    ctrl.set_obstacles([
        (25.0340, 121.5660, 20),
        (25.0325, 121.5648, 18),
    ])
else:
    ctrl.set_obstacles([])

# --------------- Map ---------------
m = folium.Map(location=[ctrl.state.lat, ctrl.state.lon], zoom_start=17,
               tiles="OpenStreetMap")

# Alternative tiles
folium.TileLayer("CartoDB positron", name="Light").add_to(m)
folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)

# Path
if len(ctrl.path) > 1:
    folium.PolyLine(ctrl.path, color="#0066ff", weight=6, opacity=0.85, tooltip="Path").add_to(m)

# Real buildings (simplified as polygons)
for poly in ctrl.building_polys[:80]:  # limit for performance
    try:
        # poly is list of (lon, lat)
        locations = [(lat, lon) for lon, lat in poly]
        folium.Polygon(locations, color="#e74c3c", weight=1,
                       fill=True, fill_opacity=0.25).add_to(m)
    except Exception:
        pass

# Circular obstacles
for olat, olon, rad in ctrl.obstacles:
    folium.Circle(location=[olat, olon], radius=rad, color="red",
                  fill=True, fill_opacity=0.3, popup="Obstacle").add_to(m)

# Start point
if ctrl.path:
    folium.CircleMarker(ctrl.path[0], radius=6, color="green",
                        fill=True, fill_color="lime", popup="Start").add_to(m)

# Robot with heading
create_heading_marker(ctrl.state.lat, ctrl.state.lon, ctrl.state.yaw).add_to(m)

folium.LayerControl().add_to(m)

st_folium(m, width=980, height=600)

# Info panels
col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Robot State")
    st.metric("Latitude", f"{ctrl.state.lat:.6f}")
    st.metric("Longitude", f"{ctrl.state.lon:.6f}")
    st.metric("Yaw (heading)", f"{ctrl.state.yaw:.1f}°")

with col_b:
    st.subheader("Executed Commands")
    if st.session_state.history:
        for h in reversed(st.session_state.history[-8:]):
            st.markdown(f"`{h['command']}`  
<span style='color:gray;font-size:0.85em'>({h['source']})</span>", unsafe_allow_html=True)
    else:
        st.info("No commands executed yet.")

st.markdown("---")
st.caption("NaVILA-Lite · Hierarchical navigation on real maps · Buildings via OSMnx · Inspired by NaVILA (RSS 2025)")
