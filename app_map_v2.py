"""
NaVILA-Lite v2 – Hierarchical navigation on real OSM maps
High-level language → mid-level commands → low-level control
Buildings = obstacles, roads = preferred paths
Fast progressive OSM: small spawn area first, expand as robot moves
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

from src.map.osm_loader import (
    load_buildings_and_roads,
    expand_around,
    needs_expansion,
    find_free_spawn,
    INITIAL_RADIUS_M,
)
from src.low_level.osm_controller import OSMController
from src.high_level.vlm_planner import MapContextPlanner
from src.high_level.geocoder import geocode
from src.high_level.router import get_osrm_route

st.set_page_config(page_title="NaVILA-Lite v2", page_icon="🗺️", layout="wide")
st.title("🗺️ NaVILA-Lite v2")
st.caption(
    "Hierarchical navigation · Progressive OSM (~100m first) · Continuous collision + stuck recovery"
)

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


def ensure_local_map(ctrl: OSMController, force_initial: bool = False):
    """
    Progressive map loading:
    - First call: load small ~100m patch around robot
    - Later: expand only when robot approaches edge of loaded area
    - If spawned inside a building → move to free space
    """
    md = st.session_state.map_data
    has_data = bool(md.get("building_coords") or md.get("success"))

    if force_initial or not has_data:
        with st.spinner(f"Loading local OSM (~{INITIAL_RADIUS_M}m around spawn)..."):
            data = load_buildings_and_roads(
                ctrl.lat, ctrl.lon, dist=INITIAL_RADIUS_M, use_cache=True, load_roads=True
            )
            st.session_state.map_data = data
            ctrl.set_map_data(data.get("buildings", []), data.get("road_graph"))

            # Exit obstacle if we spawned inside a building
            free_lat, free_lon = find_free_spawn(
                ctrl.lat, ctrl.lon, data.get("buildings", [])
            )
            if abs(free_lat - ctrl.lat) > 1e-7 or abs(free_lon - ctrl.lon) > 1e-7:
                ctrl.lat, ctrl.lon = free_lat, free_lon
                ctrl.path.append((free_lat, free_lon))
                if hasattr(ctrl, "position_history"):
                    ctrl.position_history.append((free_lat, free_lon))
                st.sidebar.info("Spawn was inside a building → moved to free space")

            if data.get("success"):
                src = "cache" if data.get("from_cache") else "live"
                st.sidebar.success(
                    f"OSM ({src}): {len(data.get('building_coords', []))} buildings "
                    f"· radius ~{data.get('radius', INITIAL_RADIUS_M)}m"
                )
            else:
                st.sidebar.warning((data.get("error") or "OSM failed")[:90])
        return

    # Expand as robot moves near the edge
    if needs_expansion(md, ctrl.lat, ctrl.lon):
        with st.spinner("Expanding map around robot..."):
            new_md = expand_around(md, ctrl.lat, ctrl.lon)
            st.session_state.map_data = new_md
            ctrl.set_map_data(new_md.get("buildings", []), new_md.get("road_graph"))
            st.sidebar.caption(
                f"Map expanded · buildings={len(new_md.get('building_coords', []))} "
                f"· radius~{new_md.get('radius', '?')}m"
            )


with st.sidebar:
    st.header("Controls")
    location_name = st.selectbox("Start Location", list(LOCATIONS.keys()))
    load_osm = st.checkbox("Load local OSM (progressive, ~100m first)", value=True)
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
        "success": False,
        "center": None,
        "radius": 0,
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
        "success": False,
        "center": None,
        "radius": 0,
    }
    st.session_state.route_waypoints = []
    st.rerun()

# Progressive OSM load / expand
if load_osm:
    ensure_local_map(ctrl, force_initial=not st.session_state.map_data.get("success"))

explanation = []

# ---- Landmark: full OSRM follow (primary path) ----
if landmark_btn and landmark.strip():
    if load_osm:
        ensure_local_map(ctrl)
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
            ctrl.follow_waypoints(waypoints, max_step_m=100.0)
            # expand map after movement
            if load_osm:
                ensure_local_map(ctrl)
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
                step = min(100.0, remaining)
                ok = ctrl.move_forward(step)
                remaining = ctrl._distance_m(ctrl.lat, ctrl.lon, tlat, tlon)
                seg += 1
                if not ok:
                    break
                if load_osm and seg % 3 == 0:
                    ensure_local_map(ctrl)
            st.session_state.history.append(f"Direct to '{landmark}'")
            explanation.append(f"State: {ctrl.get_state_summary()}")

    st.session_state.last_explanation = explanation

# ---- Language (history-aware) ----
if lang_btn and instruction.strip():
    if load_osm:
        ensure_local_map(ctrl)
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
        elif cmd.action in ("follow_road_to", "go_to_landmark"):
            ctrl.move_forward(cmd.value or 40.0)
        elif cmd.action == "stop":
            pass
        st.session_state.history.append(str(cmd))
        explanation.append(f"Executed: {cmd}")
        if load_osm:
            ensure_local_map(ctrl)

    explanation.append(f"State after: {ctrl.get_state_summary()}")
    st.session_state.last_explanation = explanation

# ---- Map ----
m = folium.Map(
    location=[ctrl.lat, ctrl.lon],
    zoom_start=16,  # closer zoom matches ~100m local area
)
folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
folium.TileLayer("CartoDB positron", name="Light").add_to(m)
folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri",
    name="Satellite",
).add_to(m)

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
st_folium(m, width=1000, height=560, key=f"map_{len(ctrl.path)}_{len(st.session_state.map_data.get('building_coords', []))}")

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
    st.subheader("Map / History")
    md = st.session_state.map_data
    st.caption(
        f"Loaded radius ~{md.get('radius', 0)}m · "
        f"buildings={len(md.get('building_coords', []))} · "
        f"roads={len(md.get('road_lines', []))}"
    )
    if st.session_state.history:
        for h in reversed(st.session_state.history[-6:]):
            st.markdown(f"- `{h}`")
    else:
        st.info("No commands yet")

st.markdown("---")
st.subheader("Explainability")
if st.session_state.last_explanation:
    for line in st.session_state.last_explanation:
        st.markdown(f"- {line}")
else:
    st.info("Execute Landmark or Language to see reasoning.")

st.caption(
    "Purple = OSRM roads · Blue = path · Red = buildings · "
    "OSM loads ~100m first, expands as you move · auto-exit if spawned in building"
)
