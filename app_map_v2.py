"""
NaVILA-Lite v2 – Modular version with Landmark + A* support
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.append(str(ROOT))

from src.map.osm_loader import load_buildings_and_roads
from src.low_level.osm_controller import OSMController
from src.high_level.vlm_planner import MapContextPlanner
from src.high_level.geocoder import geocode

st.set_page_config(page_title="NaVILA-Lite v2", page_icon="🗺️", layout="wide")
st.title("🗺️ NaVILA-Lite v2 – Hierarchical Navigation + Landmarks")
st.caption("Modular · OSM buildings/roads · Hybrid planner · Landmark navigation · A* ready")

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
                           help="Required for A* road following. Can be slow.")
    
    st.markdown("---")
    st.subheader("Landmark Navigation")
    landmark = st.text_input("Go to landmark (optional)", placeholder="e.g. Taipei Main Station")
    use_astar = st.checkbox("Use A* road following (if OSM loaded)", value=True)

    st.markdown("---")
    instruction = st.text_area(
        "Language Instruction(s)",
        value="Move forward 80 meters then turn left 90 degrees then move 50 meters",
        height=90
    )
    c1, c2 = st.columns(2)
    exec_btn = c1.button("Execute", type="primary")
    reset_btn = c2.button("Reset")

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

# Load OSM if requested
if load_osm and st.session_state.map_data.get("road_graph") is None:
    with st.spinner("Loading OSM buildings + road graph (may take time)..."):
        data = load_buildings_and_roads(ctrl.lat, ctrl.lon, dist=400)
        st.session_state.map_data = data
        ctrl.set_map_data(data.get("buildings", []), data.get("road_graph"))
        if data.get("success"):
            st.sidebar.success(f"Buildings: {len(data.get('building_coords',[]))} | Road segments: {len(data.get('road_lines',[]))}")
        else:
            st.sidebar.warning(data.get("error", "OSM load failed"))

# Execute logic
if exec_btn:
    # 1. Landmark navigation (higher priority)
    if landmark.strip():
        coords = geocode(landmark.strip())
        if coords:
            tlat, tlon = coords
            st.sidebar.info(f"Landmark found: ({tlat:.5f}, {tlon:.5f})")
            if use_astar and ctrl.road_graph is not None:
                waypoints = ctrl.plan_road_route(tlat, tlon)
                if waypoints:
                    ctrl.follow_waypoints(waypoints)
                    st.session_state.history.append(f"A* route to '{landmark}' ({len(waypoints)} nodes)")
                else:
                    # fallback straight
                    dlat = tlat - ctrl.lat
                    dlon = tlon - ctrl.lon
                    ctrl.yaw = ( __import__('math').degrees(__import__('math').atan2(dlon, dlat)) + 360) % 360
                    dist = ctrl._distance_m(ctrl.lat, ctrl.lon, tlat, tlon)
                    ctrl.move_forward(min(dist, 300))
                    st.session_state.history.append(f"Direct move toward '{landmark}' (A* unavailable)")
            else:
                dlat = tlat - ctrl.lat
                dlon = tlon - ctrl.lon
                ctrl.yaw = ( __import__('math').degrees(__import__('math').atan2(dlon, dlat)) + 360) % 360
                dist = ctrl._distance_m(ctrl.lat, ctrl.lon, tlat, tlon)
                ctrl.move_forward(min(dist, 300))
                st.session_state.history.append(f"Direct move toward '{landmark}'")
        else:
            st.sidebar.error(f"Could not geocode: {landmark}")

    # 2. Normal language commands
    if instruction.strip():
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
            st.session_state.history.append(str(cmd))

# -------------------- Map --------------------
m = folium.Map(location=[ctrl.lat, ctrl.lon], zoom_start=16)
folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
folium.TileLayer("CartoDB positron", name="Light").add_to(m)
folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri", name="Satellite"
).add_to(m)

for line in st.session_state.map_data.get("road_lines", []):
    try:
        folium.PolyLine(line, color="#f1c40f", weight=2.5, opacity=0.65).add_to(m)
    except Exception:
        pass

for coords in st.session_state.map_data.get("building_coords", []):
    try:
        folium.Polygon(coords, color="#c0392b", weight=1, fill=True, fill_opacity=0.28).add_to(m)
    except Exception:
        pass

if len(ctrl.path) > 1:
    folium.PolyLine(ctrl.path, color="#1e90ff", weight=6, opacity=0.9).add_to(m)

folium.CircleMarker(ctrl.path[0], radius=7, color="lime", fill=True, fill_color="lime", popup="Start").add_to(m)

html = f"""
<div style="transform: rotate({ctrl.yaw}deg); font-size: 24px; color: #00e676;
            text-shadow: 1px 1px 3px #000; background: rgba(0,0,0,0.45);
            border-radius: 50%; width: 30px; height: 30px;
            display: flex; align-items: center; justify-content: center;">▲</div>
"""
icon = folium.DivIcon(html=html, icon_size=(30, 30), icon_anchor=(15, 15))
folium.Marker([ctrl.lat, ctrl.lon], icon=icon, popup=f"Yaw {ctrl.yaw:.0f}°").add_to(m)

folium.LayerControl(collapsed=False).add_to(m)
st_folium(m, width=1000, height=620, key=f"v2_{len(ctrl.path)}")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Robot State")
    st.metric("Latitude", f"{ctrl.lat:.6f}")
    st.metric("Longitude", f"{ctrl.lon:.6f}")
    st.metric("Heading (0=North)", f"{ctrl.yaw:.1f}°")
    st.write(f"Buildings: {len(st.session_state.map_data.get('building_coords', []))} | "
             f"Roads: {len(st.session_state.map_data.get('road_lines', []))}")

with col2:
    st.subheader("History")
    if st.session_state.history:
        for h in reversed(st.session_state.history[-12:]):
            st.markdown(f"- `{h}`")
    else:
        st.info("No commands yet")

st.markdown("---")
st.markdown("""
**v2 Capabilities**
- Hierarchical language commands
- Landmark navigation via Nominatim ("Go to Taipei Main Station")
- Optional A* road following when OSM road graph is loaded
- Buildings = obstacles, Roads = preferred paths
- Modular codebase ready for further VLM integration
""")
