"""
NaVILA-Lite v2 – Modular version (Option A)
Uses:
- src/map/osm_loader.py
- src/low_level/osm_controller.py
- src/high_level/vlm_planner.py
- src/high_level/geocoder.py
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
import sys
from pathlib import Path

# Make sure src is importable
ROOT = Path(__file__).parent
sys.path.append(str(ROOT))

from src.map.osm_loader import load_buildings_and_roads, point_in_buildings
from src.low_level.osm_controller import OSMController
from src.high_level.vlm_planner import MapContextPlanner, MidLevelCommand
from src.high_level.geocoder import geocode

st.set_page_config(page_title="NaVILA-Lite v2", page_icon="🗺️", layout="wide")
st.title("🗺️ NaVILA-Lite v2 – Map-Context Hierarchical Navigation")
st.caption("Modular · Buildings as obstacles · Roads visualized · Hybrid planner · A* ready")

LOCATIONS = {
    "Taipei 101": (25.0339, 121.5640),
    "National Taiwan University": (25.0170, 121.5375),
    "Taipei Main Station": (25.0478, 121.5170),
    "Kaohsiung": (22.6275, 120.3010),
    "Bangalore MG Road": (12.9760, 77.6060),
    "Open Field": (25.0510, 121.5810),
}

with st.sidebar:
    st.header("Controls")
    location_name = st.selectbox("Start Location", list(LOCATIONS.keys()))
    load_osm = st.checkbox("Load OSM (buildings + roads)", value=False,
                           help="Can be slow / timeout. Leave off for fast testing.")
    instruction = st.text_area(
        "Language Instruction(s)",
        value="Move forward 80 meters then turn left 90 degrees then move 50 meters",
        height=100
    )
    c1, c2 = st.columns(2)
    exec_btn = c1.button("Execute", type="primary")
    reset_btn = c2.button("Reset")

# Session state
if "ctrl" not in st.session_state:
    lat, lon = LOCATIONS["Taipei 101"]
    st.session_state.ctrl = OSMController(lat, lon)
    st.session_state.planner = MapContextPlanner()
    st.session_state.history = []
    st.session_state.loc = "Taipei 101"
    st.session_state.map_data = {"building_coords": [], "road_lines": [], "buildings": [], "road_graph": None}

ctrl: OSMController = st.session_state.ctrl

if reset_btn or location_name != st.session_state.loc:
    lat, lon = LOCATIONS[location_name]
    ctrl.reset(lat, lon)
    st.session_state.history = []
    st.session_state.loc = location_name
    st.session_state.map_data = {"building_coords": [], "road_lines": [], "buildings": [], "road_graph": None}
    st.rerun()

# Optional OSM load
if load_osm and len(st.session_state.map_data["building_coords"]) == 0:
    with st.spinner("Loading OSM buildings + roads (may timeout)..."):
        data = load_buildings_and_roads(ctrl.lat, ctrl.lon, dist=300)
        st.session_state.map_data = data
        ctrl.set_map_data(data.get("buildings", []), data.get("road_graph"))
        if data.get("success"):
            st.sidebar.success(f"Buildings: {len(data['building_coords'])} | Roads: {len(data['road_lines'])}")
        else:
            st.sidebar.warning(f"OSM issue: {data.get('error', 'unknown')}")

# Execute
if exec_btn and instruction.strip():
    cmds = st.session_state.planner.parse(instruction)
    for cmd in cmds:
        if cmd.action == "move_forward":
            ctrl.move_forward(cmd.value or 30.0)
        elif cmd.action == "turn_left":
            ctrl.turn_left(cmd.value or 90.0)
        elif cmd.action == "turn_right":
            ctrl.turn_right(cmd.value or 90.0)
        elif cmd.action == "return_home":
            ctrl.return_home()
        elif cmd.action == "stop":
            pass
        st.session_state.history.append(str(cmd))

# --------------- Map ---------------
m = folium.Map(location=[ctrl.lat, ctrl.lon], zoom_start=17)
folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
folium.TileLayer("CartoDB positron", name="Light").add_to(m)
folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri", name="Satellite"
).add_to(m)

# Roads
for line in st.session_state.map_data.get("road_lines", []):
    try:
        folium.PolyLine(line, color="#f1c40f", weight=3, opacity=0.7).add_to(m)
    except Exception:
        pass

# Buildings
for coords in st.session_state.map_data.get("building_coords", []):
    try:
        folium.Polygon(coords, color="#c0392b", weight=1, fill=True, fill_opacity=0.3).add_to(m)
    except Exception:
        pass

# Path
if len(ctrl.path) > 1:
    folium.PolyLine(ctrl.path, color="#1e90ff", weight=6, opacity=0.9).add_to(m)

folium.CircleMarker(ctrl.path[0], radius=7, color="lime", fill=True, fill_color="lime", popup="Start").add_to(m)

# Robot marker
html = f"""
<div style="transform: rotate({ctrl.yaw}deg); font-size: 24px; color: #00e676;
            text-shadow: 1px 1px 3px #000; background: rgba(0,0,0,0.4);
            border-radius: 50%; width: 30px; height: 30px;
            display: flex; align-items: center; justify-content: center;">▲</div>
"""
icon = folium.DivIcon(html=html, icon_size=(30, 30), icon_anchor=(15, 15))
folium.Marker([ctrl.lat, ctrl.lon], icon=icon, popup=f"Yaw {ctrl.yaw:.0f}°").add_to(m)

folium.LayerControl(collapsed=False).add_to(m)
st_folium(m, width=1000, height=600, key=f"v2map_{len(ctrl.path)}")

# Info
col1, col2 = st.columns(2)
with col1:
    st.subheader("Robot State")
    st.metric("Latitude", f"{ctrl.lat:.6f}")
    st.metric("Longitude", f"{ctrl.lon:.6f}")
    st.metric("Heading (0=North)", f"{ctrl.yaw:.1f}°")
    st.write(f"Buildings: {len(st.session_state.map_data.get('building_coords', []))} | "
             f"Roads: {len(st.session_state.map_data.get('road_lines', []))}")

with col2:
    st.subheader("Executed Commands")
    if st.session_state.history:
        for h in reversed(st.session_state.history[-10:]):
            st.code(h, language=None)
    else:
        st.info("No commands yet")

st.markdown("---")
st.markdown("""
**NaVILA-Lite v2 Architecture**
- High-level: Map-Context Hybrid Planner
- Low-level: OSMController (reactive + A* ready)
- Map: OSMnx buildings (obstacles) + road graph
- This version is modular and ready for further VLM / A* upgrades.
""")
