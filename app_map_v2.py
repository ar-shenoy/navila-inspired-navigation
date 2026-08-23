"""
NaVILA-Lite v2 – Final modular version
- Hierarchical planner (heuristic + optional VLM)
- OSM buildings/roads with better caching
- Landmark + A*
- Movement quality score
- Explainability
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
import sys
from pathlib import Path
import math
import os

ROOT = Path(__file__).parent
sys.path.append(str(ROOT))

from src.map.osm_loader import load_buildings_and_roads
from src.low_level.osm_controller import OSMController
from src.high_level.vlm_planner import MapContextPlanner
from src.high_level.geocoder import geocode

st.set_page_config(page_title="NaVILA-Lite v2", page_icon="🗺️", layout="wide")
st.title("🗺️ NaVILA-Lite v2")
st.caption("Hierarchical VLA-style navigation · Map semantics · Landmark · Score · Explainable")

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
    load_osm = st.checkbox("Load OSM (buildings + roads)", value=False)
    use_vlm = st.checkbox("Try lightweight VLM (needs HF_TOKEN)", value=False,
                          help="Optional. Set HF_TOKEN env var. Falls back to heuristic.")

    st.markdown("---")
    landmark = st.text_input("Go to landmark", placeholder="e.g. Taipei Main Station")
    use_astar = st.checkbox("Prefer A* road following", value=True)

    st.markdown("---")
    instruction = st.text_area(
        "Language Instruction(s)",
        value="Move forward 70 meters then turn left 90 degrees then move 40 meters",
        height=90
    )
    c1, c2 = st.columns(2)
    exec_btn = c1.button("Execute", type="primary")
    reset_btn = c2.button("Reset")

if "ctrl" not in st.session_state:
    lat, lon = LOCATIONS["Taipei 101"]
    st.session_state.ctrl = OSMController(lat, lon)
    st.session_state.planner = MapContextPlanner(use_vlm=False)
    st.session_state.history = []
    st.session_state.loc = "Taipei 101"
    st.session_state.map_data = {"building_coords": [], "road_lines": [], "buildings": [], "road_graph": None}
    st.session_state.last_explanation = []

ctrl: OSMController = st.session_state.ctrl
st.session_state.planner.use_vlm = use_vlm

if reset_btn or location_name != st.session_state.loc:
    lat, lon = LOCATIONS[location_name]
    ctrl.reset(lat, lon)
    st.session_state.history = []
    st.session_state.last_explanation = []
    st.session_state.loc = location_name
    st.session_state.map_data = {"building_coords": [], "road_lines": [], "buildings": [], "road_graph": None}
    st.rerun()

if load_osm and st.session_state.map_data.get("road_graph") is None:
    with st.spinner("Loading OSM (cached when possible)..."):
        data = load_buildings_and_roads(ctrl.lat, ctrl.lon, dist=350)
        st.session_state.map_data = data
        ctrl.set_map_data(data.get("buildings", []), data.get("road_graph"))
        if data.get("success"):
            st.sidebar.success(f"Buildings: {len(data.get('building_coords',[]))} | Roads: {len(data.get('road_lines',[]))}")
        else:
            st.sidebar.warning(data.get("error", "OSM load failed"))

explanation = []

if exec_btn:
    map_ctx = st.session_state.planner.build_map_context_summary(
        len(st.session_state.map_data.get("building_coords", [])),
        len(st.session_state.map_data.get("road_lines", [])),
        ctrl.lat, ctrl.lon
    )

    if landmark.strip():
        coords = geocode(landmark.strip())
        if coords:
            tlat, tlon = coords
            explanation.append(f"Geocoded '{landmark}' → ({tlat:.5f}, {tlon:.5f})")
            if use_astar and ctrl.road_graph is not None:
                waypoints = ctrl.plan_road_route(tlat, tlon)
                if waypoints:
                    ctrl.follow_waypoints(waypoints)
                    explanation.append(f"A* route ({len(waypoints)} nodes)")
                    st.session_state.history.append(f"A* to '{landmark}'")
                else:
                    dlat, dlon = tlat - ctrl.lat, tlon - ctrl.lon
                    ctrl.yaw = (math.degrees(math.atan2(dlon, dlat)) + 360) % 360
                    dist = ctrl._distance_m(ctrl.lat, ctrl.lon, tlat, tlon)
                    ctrl.move_forward(min(dist, 250))
                    explanation.append("A* unavailable → direct movement")
                    st.session_state.history.append(f"Direct to '{landmark}'")
            else:
                dlat, dlon = tlat - ctrl.lat, tlon - ctrl.lon
                ctrl.yaw = (math.degrees(math.atan2(dlon, dlat)) + 360) % 360
                dist = ctrl._distance_m(ctrl.lat, ctrl.lon, tlat, tlon)
                ctrl.move_forward(min(dist, 250))
                explanation.append("Direct movement")
                st.session_state.history.append(f"Direct to '{landmark}'")
        else:
            explanation.append(f"Geocoding failed for '{landmark}'")

    if instruction.strip():
        cmds = st.session_state.planner.parse(instruction, map_context=map_ctx)
        explanation.append(f"Planner produced {len(cmds)} command(s) (source: {cmds[0].source if cmds else 'none'})")
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
            explanation.append(f"Executed: {cmd}")

    st.session_state.last_explanation = explanation

# Map
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

folium.CircleMarker(ctrl.path[0], radius=7, color="lime", fill=True, fill_color="lime").add_to(m)

html = f"""
<div style="transform: rotate({ctrl.yaw}deg); font-size: 24px; color: #00e676;
            text-shadow: 1px 1px 3px #000; background: rgba(0,0,0,0.45);
            border-radius: 50%; width: 30px; height: 30px;
            display: flex; align-items: center; justify-content: center;">▲</div>
"""
icon = folium.DivIcon(html=html, icon_size=(30, 30), icon_anchor=(15, 15))
folium.Marker([ctrl.lat, ctrl.lon], icon=icon, popup=f"Yaw {ctrl.yaw:.0f}°").add_to(m)

folium.LayerControl(collapsed=False).add_to(m)
st_folium(m, width=1000, height=580, key=f"v2_{len(ctrl.path)}")

col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("Robot State")
    st.metric("Latitude", f"{ctrl.lat:.6f}")
    st.metric("Longitude", f"{ctrl.lon:.6f}")
    st.metric("Heading", f"{ctrl.yaw:.1f}°")

with col2:
    st.subheader("Performance")
    st.metric("Movement Score", f"{ctrl.score:.1f}")
    st.metric("Distance", f"{ctrl.total_distance:.0f} m")
    st.metric("Collisions", ctrl.collision_count)

with col3:
    st.subheader("History")
    if st.session_state.history:
        for h in reversed(st.session_state.history[-8:]):
            st.markdown(f"- `{h}`")
    else:
        st.info("No commands yet")

st.markdown("---")
st.subheader("Explainability")
if st.session_state.last_explanation:
    for line in st.session_state.last_explanation:
        st.markdown(f"- {line}")
else:
    st.info("Execute a command to see the reasoning trace.")

st.caption("NaVILA-Lite v2 · Hierarchical navigation on real maps · Inspired by NaVILA (RSS 2025)")
