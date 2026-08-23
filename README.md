# NaVILA-Lite

**Practical hierarchical Vision-Language Navigation on real maps**

A lightweight system inspired by [NaVILA (RSS 2025)](https://navila-bot.github.io/).  
It keeps the core hierarchical idea — **high-level language → mid-level spatial commands → low-level control** — while running on limited consumer hardware (no NVIDIA Isaac Sim required).

---

## Why this project exists

Full NaVILA-style systems typically rely on heavy simulation (e.g. Isaac Sim) and strong GPUs.  
This prototype explores the same hierarchical interface under real constraints:

- AMD / limited-GPU laptop
- No Isaac Sim access
- Need for a runnable, demonstrable demo

The result is a **map-grounded** hierarchical navigator using OpenStreetMap, OSRM road routing, and a Streamlit interface.

---

## Quick start

```bash
git clone https://github.com/ar-shenoy/navila-inspired-navigation.git
cd navila-inspired-navigation
pip install -r requirements_map.txt
streamlit run app_map_v2.py
```

**Main entry point:** `app_map_v2.py`

Suggested first demo:

1. Leave “Live OSM scan expand” **off** (faster)
2. Start at **Taipei 101**
3. Language: `Move forward 70 meters then turn left 90 degrees then move 40 meters` → **Execute Language**
4. Landmark: `Taipei Main Station` → **Execute Landmark**

---

## Architecture

```text
Natural language instruction  OR  landmark name
              │
              ▼
┌─────────────────────────────────────┐
│  High-level planner                 │
│  (hybrid heuristic + optional VLM)  │
└─────────────────────────────────────┘
              │  mid-level commands
              ▼
┌─────────────────────────────────────┐
│  Low-level controller               │
│  (reactive motion + route following)│
└─────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  Real map layer                     │
│  • OSRM → road routes (purple)      │
│  • Prebaked local buildings         │
│  • Optional live OSM expand         │
└─────────────────────────────────────┘
```

### Design choices

| Choice | Reason |
|--------|--------|
| Hierarchical commands | Same core insight as NaVILA — interpretable mid-level interface |
| Hybrid planner | Reliable on limited hardware; VLM optional |
| OSRM public routing | Open-source real-road paths without heavy local graphs |
| Prebaked obstacles | Instant demo start; avoids Overpass timeouts |
| Streamlit + Folium | Shareable interactive demo without Isaac Sim |

---

## Features

- Hierarchical NaVILA-style command flow
- Multi-command natural language instructions
- Landmark navigation via Nominatim + **OSRM** road routes
- Instant **prebaked** building obstacles for listed spawn maps
- Optional live OSM expand while moving (off by default for speed)
- Separate execute buttons for landmark vs language
- Movement score, collision count, explainability panel
- Optional lightweight VLM (Hugging Face token via env / secrets)
- Modular code under `src/`

---

## Project structure

```text
navila-inspired-navigation/
├── app_map_v2.py                 ← Main Streamlit app
├── requirements_map.txt
├── data/preloaded/               ← Instant obstacle packs for demo maps
├── src/
│   ├── high_level/
│   │   ├── vlm_planner.py        # Hybrid / map-context planner
│   │   ├── geocoder.py           # Nominatim landmarks
│   │   └── router.py             # OSRM road routing
│   ├── low_level/
│   │   └── osm_controller.py     # Motion, avoidance, route following
│   └── map/
│       ├── prebaked.py           # Instant local obstacles
│       └── osm_loader.py         # Optional live OSM expand
├── docs/                         # Notes and analysis
└── notebooks/                    # Early concept experiments
```

Legacy prototypes (`app.py`, `app_map.py`) are kept only for history; **use `app_map_v2.py`**.

---

## Honest limitations

- This is **not** a full trained VLA model and **not** an Isaac Sim deployment.
- High-level planning is heuristic-dominant by default; VLM is optional and network-dependent.
- Dense real-time obstacle fields over long distances are constrained by public Overpass latency — addressed with prebaked local packs + OSRM roads rather than continuous city-scale OSMnx downloads.
- Collision checking is geometric, not full semantic scene understanding.
- Long routes follow OSRM road geometry; local building avoidance is strongest near prebaked / expanded regions.

These limits are deliberate trade-offs so the system stays **runnable, explainable, and demonstrable** on consumer hardware.

---

## Future work

- Stronger local / instruction-tuned VLM with map context
- Richer evaluation (success rate, path efficiency, collision rate)
- Bridge toward Isaac Sim or real robot low-level control when hardware allows

---

## Citation / inspiration

Cheng et al., *NaVILA: Legged Robot Vision-Language-Action Model for Navigation*, RSS 2025.

This project is an independent practical exploration of hierarchical VLN ideas under hardware constraints, not an official NaVILA implementation.
