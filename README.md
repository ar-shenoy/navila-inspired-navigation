# NaVILA-Lite

**Practical Hierarchical Vision-Language Navigation on Real Maps**

Inspired by [NaVILA (RSS 2025)](https://navila-bot.github.io/).  
This project implements a hierarchical navigation system (High-level language → mid-level commands → low-level control) that runs on limited hardware and uses real OpenStreetMap data.

---

## Quick Start

```bash
git clone https://github.com/ar-shenoy/navila-inspired-navigation.git
cd navila-inspired-navigation
pip install -r requirements_map.txt
streamlit run app_map_v2.py
```

> **Main entry point:** `app_map_v2.py`  
> (Older experimental versions: `app_map.py`, `app.py`)

**First run recommendation:**
1. Leave “Load OSM” unchecked for fast testing
2. Click Reset
3. Enter: `Move forward 60 meters then turn left 90 degrees then move 40 meters`
4. Press Execute

---

## Architecture

```text
Natural Language / Landmark
          ↓
High-Level Planner (Hybrid heuristic + optional VLM)
          ↓  mid-level commands
Low-Level Controller (Reactive + optional A*)
          ↓
OpenStreetMap Environment
  - building=*  → obstacles
  - highway=*   → preferred paths
```

---

## Features

- Hierarchical NaVILA-style design
- Multi-command natural language instructions
- Landmark navigation (Nominatim)
- Optional A* road following
- OSM buildings as obstacles / roads as preferred paths
- Movement quality score
- Explainability panel
- Optional lightweight VLM (Hugging Face Inference API)
- Modular codebase under `src/`

---

## Project Structure

```text
navila-inspired-navigation/
├── app_map_v2.py                 ← Main Streamlit app (use this)
├── app_map.py                    ← Older version
├── src/
│   ├── high_level/
│   │   ├── vlm_planner.py
│   │   └── geocoder.py
│   ├── low_level/
│   │   └── osm_controller.py
│   └── map/
│       └── osm_loader.py
├── requirements_map.txt
└── README.md
```

---

## Design Decisions

| Decision | Reason |
|----------|--------|
| Hierarchical commands | Core insight from NaVILA |
| Hybrid planner | Reliability on limited hardware |
| OSM semantic layers | Real buildings vs roads |
| Optional A* | Better paths when road graph is available |
| Explainability panel | Makes the system inspectable |
| Modular `src/` | Easier to extend |

---

## Limitations (Honest)

- High-level planner is heuristic-dominant by default for stability. VLM is optional.
- Public Overpass API can timeout; OSM loading is optional.
- A* depends on successful road-graph download.
- Collision checking is geometric.
- This is a research-oriented prototype focused on hierarchical design and real-map demonstration.

---

## Future Work

- Stronger instruction-tuned VLM with map context
- Improved road-following behavior
- Trajectory evaluation metrics
- Path toward Isaac Sim / real robots

---

**Inspired by:** Cheng et al., *NaVILA: Legged Robot Vision-Language-Action Model for Navigation*, RSS 2025.
