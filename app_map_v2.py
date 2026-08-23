"""
NaVILA-Lite v2 – Hierarchical navigation on real OSM maps
High-level language → mid-level commands → low-level control
Buildings = obstacles, roads = preferred paths
Fully end-to-end, no hardcoded scenarios
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
from src.high_level.router import get_osrm_route

st.set_page_config(page_title="NaVILA-Lite v2", page_icon="🗺️", layout="wide")
st.title("🗺️ NaVILA-Lite v2")
st.caption("Hierarchical navigation · OSRM road following · Continuous collision + stuck recovery · History-aware")

LOCATIONS = {
    "Taipei 101": (25.0339, 121.5640),
    "National Taiwan University": (25.0170, 121.5375),
    "Taipei Main Station": (25.0478, 121.5170),
    "Kaohsiung": (22.6275, 120.3010),
    "Tainan": (23.0005, 120.2270),
    "Bangalore MG Road": (12.9760, 77.6060),
    "Open Field": (25.0510, 121.5810),
}


def get_hf_token():
    try:
        return st.secrets.get("HF_TOKEN", None)
    except Exception:
        pass
    return os.environ.get("HF_TOKEN", None)


with st.sidebar:
    st.header("Controls")
    location_name = st.selectbox("Start Location", list(LOCATIONS.keys()))
    load_osm = st.checkbox("Load local OSM (cached when possible)", value=False)
    use_vlm = st.checkbox("Try lightweight VLM", value=False)

    st.markdown("---")
    st.subheader("1. Landmark Navigation")
    landmark = st.text_input("Go to landmark", placeholder="e.g. Taipei 101 / Taipei Main Station")
    landmark_btn = st.button("Execute Landmark", type="primary")

    st.markdown("---")
    st.subheader("2. Language Instructions")
    instruction = st.text_area(
        "Language Instruction(s)",
        value="Move forward 70 meters then turn left 90 degrees then move 40 meters",
        height=90,
    )
    lang_btn = st.button("Execute Language")

    st.markdown("---")
    reset_btn = st.button("Reset to Location")

if "ctrl" not in st.session_state:
    lat, lon = LOCATIONS["Taipei 101"]
    st.session_state.ctrl = OSMController(lat, lon)
    st.session_state.planner = MapContextPlanner(use_vlm=False, hf_token=get_hf_token())
    st.session_state.history = []
    st.session_state.loc = "Taipei 101"
    st.session_state.map_data = {
        "building_coords": [],
        "road_lines": [],
        "buildings": [],
        "road_graph": None,
    }
    st.session_state.last_explanation = []
    st.session_state.route_waypoints = []

ctrl: OSMController = st.session_state.ctrl
st.session_state.planner.use_vlm = use_vlm
st.session_state.planner.hf_token = get_hf_token()

if reset_btn or location_name != st.session_state.loc:
    lat, lon = LOCATIONS[location_name]
    ctrl.reset(lat, lon)
    st.session_state.history = []
    st.session_state.last_explanation = []
    st.session_state.loc = location_name
    st.session_state.map_data = {
        "building_coords": [],
        "road_lines": [],
        "buildings": [],
        "road_graph": None,
    }
    st.session_state.route_waypoints = []
    st.rerun()

if load_osm and not st.session_state.map_data.get("building_coords"):
    with st.spinner("Loading local OSM (disk + memory cache)..."):
        data = load_buildings_and_roads(ctrl.lat, ctrl.lon, dist=250)
        st.session_state.map_data = data
        ctrl.set_map_data(data.get("buildings", []), data.get("road_graph"))
        if data.get("success"):
            src = "cache" if data.get("from_cache") else "live Overpass"
            st.sidebar.success(f"OSM ({src}): {len(data.get('building_coords', []))} buildings")
        else:
            st.sidebar.warning(data.get("error", "OSM failed")[:80])

explanation = []

# ---- Landmark: full OSRM follow (primary path) ----
if landmark_btn and landmark.strip():
    coords = geocode(landmark.strip())
    if coords is None:
        explanation.append(f"Could not geocode '{landmark}'")
        st.sidebar.error("Landmark not found")
    else:
        tlat, tlon = coords
        dist = ctrl._distance_m(ctrl.lat, ctrl.lon, tlat, tlon)
        explanation.append(f"Target: '{landmark}' ({tlat:.5f}, {tlon:.5f})")
        explanation.append(f"Distance: {dist/1000:.2f} km")

        with st.spinner("Fetching OSRM road route..."):
            waypoints = get_osrm_route(ctrl.lat, ctrl.lon, tlat, tlon, max_waypoints=120)

        if waypoints and len(waypoints) > 1:
            st.session_state.route_waypoints = waypoints
            explanation.append(f"OSRM route: {len(waypoints)} waypoints (prefer roads)")
            # Primary: follow complete road route with continuous collision + stuck recovery
            ctrl.follow_waypoints(waypoints, max_step_m=120.0)
            final_dist = ctrl._distance_m(ctrl.lat, ctrl.lon, tlat, tlon)
            explanation.append(f"Route followed. Remaining to target: {final_dist:.0f} m")
            explanation.append(f"State: {ctrl.get_state_summary()}")
            st.session_state.history.append(f"OSRM full route to '{landmark}'")
        else:
            explanation.append("OSRM failed → direct segmented movement with recovery")
            remaining = dist
            seg = 0
            while remaining > 25 and seg < 80:
                dlat = tlat - ctrl.lat
                dlon = tlon - ctrl.lon
                ctrl.yaw = (math.degrees(math.atan2(dlon, dlat)) + 360) % 360
                step = min(120.0, remaining)
                ok = ctrl.move_forward(step)
                remaining = ctrl._distance_m(ctrl.lat, ctrl.lon, tlat, tlon)
                seg += 1
                if not ok:
                    break
            st.session_state.history.append(f"Direct to '{landmark}'")
            explanation.append(f"State: {ctrl.get_state_summary()}")

    st.session_state.last_explanation = explanation

# ---- Language (history-aware) ----
if lang_btn and instruction.strip():
    state_sum = ctrl.get_state_summary()
    map_ctx = st.session_state.planner.build_map_context_summary(
        len(st.session_state.map_data.get("building_coords", [])),
        len(st.session_state.map_data.get("road_lines", [])),
        ctrl.lat,
        ctrl.lon,
        state_summary=state_sum,
    )
    cmds = st.session_state.planner.parse(instruction, map_context=map_ctx)
    explanation.append(f"Parsed {len(cmds)} cmd(s) · source={cmds[0].source if cmds else '?'}")
    explanation.append(f"Context used: {map_ctx[:120]}...")

    for cmd in cmds:
        if cmd.action == "move_forward":
            ctrl.move_forward(cmd.value or 30.0)
        elif cmd.action == "turn_left":
            ctrl.turn_left(cmd.value or 90.0)
        elif cmd.action == "turn_right":
            ctrl.turn_right(cmd.value or 90.0)
        elif cmd.action == "return_home":
            ctrl.return_home()
        elif cmd.action == "follow_road_to":
            # If we have a road graph, try a short road-preferring step toward current heading
            if ctrl.road_graph is not None:
                # simple: move forward while preferring roads (already handled by collision + recovery)
                ctrl.move_forward(cmd.value or 40.0)
            else:
                ctrl.move_forward(cmd.value or 40.0)
        elif cmd.action == "go_to_landmark":
            # treat as extra forward if no separate landmark flow triggered
            ctrl.move_forward(cmd.value or 50.0)
        elif cmd.action == "stop":
            pass
        st.session_state.history.append(str(cmd))
        explanation.append(f"Executed: {cmd}")

    explanation.append(f"State after: {ctrl.get_state_summary()}")
    st.session_state.last_explanation = explanation

# ---- Map ----
m = folium.Map(
    location=[ctrl.lat, ctrl.lon],
    zoom_start=12 if len(st.session_state.route_waypoints) > 40 else 15,
)
folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
folium.TileLayer("CartoDB positron", name="Light").add_to(m)
folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri",
    name="Satellite",
).add_to(m)

# Purple = OSRM planned road route
if st.session_state.route_waypoints:
    try:
        folium.PolyLine(
            st.session_state.route_waypoints,
            color="#9b59b6",
            weight=4,
            opacity=0.7,
            popup="OSRM plan (prefer roads)",
        ).add_to(m)
    except Exception:
        pass

for line in st.session_state.map_data.get("road_lines", []):
    try:
        folium.PolyLine(line, color="#f1c40f", weight=2, opacity=0.5).add_to(m)
    except Exception:
        pass

for coords in st.session_state.map_data.get("building_coords", []):
    try:
        folium.Polygon(coords, color="#c0392b", weight=1, fill=True, fill_opacity=0.25).add_to(m)
    except Exception:
        pass

if len(ctrl.path) > 1:
    folium.PolyLine(ctrl.path, color="#1e90ff", weight=5, opacity=0.9).add_to(m)

folium.CircleMarker(
    ctrl.path[0], radius=7, color="lime", fill=True, fill_color="lime", popup="Start"
).add_to(m)

html = f"""
<div style="transform: rotate({ctrl.yaw}deg); font-size: 24px; color: #00e676;
            text-shadow: 1px 1px 3px #000; background: rgba(0,0,0,0.45);
            border-radius: 50%; width: 30px; height: 30px;
            display: flex; align-items: center; justify-content: center;">▲</div>
"""
icon = folium.DivIcon(html=html, icon_size=(30, 30), icon_anchor=(15, 15))
folium.Marker([ctrl.lat, ctrl.lon], icon=icon, popup=f"Yaw {ctrl.yaw:.0f}°").add_to(m)

folium.LayerControl(collapsed=False).add_to(m)
st_folium(m, width=1000, height=560, key=f"map_{len(ctrl.path)}")

col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("Robot State")
    st.metric("Latitude", f"{ctrl.lat:.6f}")
    st.metric("Longitude", f"{ctrl.lon:.6f}")
    st.metric("Heading", f"{ctrl.yaw:.1f}°")

with col2:
    st.subheader("Performance")
    st.metric("Score", f"{ctrl.score:.1f}")
    st.metric("Distance", f"{ctrl.total_distance:.0f} m")
    st.metric("Collisions", ctrl.collision_count)
    if ctrl.total_distance > 1:
        efficiency = max(0.0, 1.0 - (ctrl.collision_count * 8.0) / ctrl.total_distance)
        st.metric("Path efficiency (live)", f"{efficiency:.2f}")

with col3:
    st.subheader("History")
    if st.session_state.history:
        for h in reversed(st.session_state.history[-8:]):
            st.markdown(f"- `{h}`")
    else:
        st.info("No commands yet")
    st.caption(ctrl.get_state_summary()[:90] + "...")

st.markdown("---")
st.subheader("Explainability")
if st.session_state.last_explanation:
    for line in st.session_state.last_explanation:
        st.markdown(f"- {line}")
else:
    st.info("Execute Landmark or Language to see reasoning.")

st.caption(
    "Purple = OSRM planned roads · Blue = actual path · Red polygons = buildings (obstacles) · "
    "Continuous collision + stuck recovery · History fed to planner"
)
