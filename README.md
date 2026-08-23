# NaVILA-Lite

**Practical Hierarchical Vision-Language Navigation on Real Maps**

A modular, hierarchical navigation system inspired by [NaVILA (RSS 2025)](https://navila-bot.github.io/).  
It keeps the core idea of separating high-level language reasoning from low-level control, while adding real-world map semantics and making the system runnable on limited hardware.

---

## Key Idea

NaVILA showed that mid-level spatial commands are an effective interface between vision-language models and low-level controllers.  
NaVILA-Lite applies the same hierarchical principle in a practical outdoor setting:

```text
Natural Language / Landmark
          ↓
High-Level Planner (Hybrid / Map-Context)
          ↓  mid-level commands
Low-Level Controller (Reactive + optional A*)
          ↓
Real Map (OpenStreetMap)
  - building=*  → obstacles
  - highway=*   → preferred paths
```

---

## Features

- Hierarchical NaVILA-style architecture
- Multi-command natural language instructions
- Landmark navigation (Nominatim geocoding)
- Optional A* road-graph following
- OpenStreetMap integration:
  - Buildings as hard obstacles
  - Roads as preferred traversable paths
- Dynamic map data loading with caching
- Explainability panel (shows why actions were taken)
- Multiple map layers
- Modular codebase (`src/`)

---

## Quick Start

```bash
git clone https://github.com/ar-shenoy/navila-inspired-navigation.git
cd navila-inspired-navigation
pip install -r requirements_map.txt
streamlit run app_map_v2.py
```

**Recommended first run:**
1. Leave “Load OSM” unchecked
2. Click Reset
3. Enter a multi-command instruction and press Execute
4. Later enable OSM for buildings + roads + A*

---

## Project Structure

```text
navila-inspired-navigation/
├── app_map_v2.py                  # Main Streamlit application
├── src/
│   ├── high_level/
│   │   ├── vlm_planner.py         # Hybrid / Map-Context planner
│   │   └── geocoder.py            # Nominatim landmark lookup
│   ├── low_level/
│   │   └── osm_controller.py      # Movement + A* + collision
│   └── map/
│       └── osm_loader.py          # Buildings + road graph loader
├── requirements_map.txt
└── README.md
```

---

## Design Decisions

| Decision                        | Reason |
|--------------------------------|--------|
| Hierarchical commands          | Core NaVILA insight – interpretable & modular |
| Hybrid planner                 | Reliability on limited hardware |
| OSM semantic layers            | Real buildings vs roads instead of synthetic obstacles |
| Optional A*                    | Better path quality when road graph is available |
| Explainability panel           | Makes the system inspectable and demo-friendly |
| Modular `src/` structure       | Easier to extend toward real VLM or Isaac Sim |

---

## Limitations (Honest)

- High-level planner is currently heuristic-dominant for stability. A lightweight VLM can be added later.
- Public Overpass API can timeout; OSM loading is optional.
- A* depends on successful road-graph download.
- Collision checking is geometric, not full semantic scene understanding.
- This is a research-oriented prototype focused on hierarchical design and real-map demonstration, not a full trained VLA model.

---

## Future Work

- Plug in a small instruction-tuned VLM with map-context prompting
- Stronger road-following bias / lane-level behavior
- Trajectory evaluation metrics
- Bridge to Isaac Sim / real robot deployment

---

## Relation to NaVILA

This project intentionally keeps the hierarchical structure proposed by NaVILA while exploring how far the idea can go with real outdoor maps and constrained compute. It is designed as a clear, runnable stepping stone rather than a full reproduction of the original system.

---

**Inspired by:** Cheng et al., *NaVILA: Legged Robot Vision-Language-Action Model for Navigation*, RSS 2025.
