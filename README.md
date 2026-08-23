# NaVILA-Lite

**Practical Hierarchical Vision-Language Navigation on Real Maps**

A lightweight, hierarchical navigation system inspired by [NaVILA (RSS 2025)](https://navila-bot.github.io/).  
This project demonstrates the core NaVILA insight — separating high-level language reasoning from low-level control — while making it runnable on limited hardware and demonstrable through an interactive map-based interface.

---

## Motivation

Full Vision-Language-Action models such as NaVILA are powerful but require heavy simulation (Isaac Sim) and significant compute.  
NaVILA-Lite explores a practical middle ground:

- Keep the **hierarchical architecture** (High-level → Mid-level commands → Low-level execution)
- Make it work on free / consumer hardware
- Add real-world map semantics (OpenStreetMap buildings vs roads)
- Provide an interactive, shareable demo

The goal is to show clear understanding of hierarchical VLA design while delivering something that can actually be run, demonstrated, and extended.

---

## Architecture

```text
Natural Language Instruction
          │
          ▼
┌─────────────────────────────┐
│   High-Level Planner        │  (Hybrid: Heuristic + VLM-ready)
│   - Multi-command parsing   │
│   - move / turn / stop /    │
│     return_home             │
└─────────────────────────────┘
          │
          ▼  Mid-level commands
┌─────────────────────────────┐
│   Low-Level Controller      │
│   - Heading-aware movement  │
│   - Reactive avoidance      │
│   - Path memory             │
└─────────────────────────────┘
          │
          ▼
┌─────────────────────────────┐
│   Map Environment (Folium)  │
│   - OpenStreetMap           │
│   - building=* = obstacles  │
│   - highway=* = roads       │
└─────────────────────────────┘
```

### Design Decisions

| Component              | Choice                              | Reason |
|------------------------|-------------------------------------|--------|
| High-level planner     | Hybrid (heuristic primary)          | Reliability on limited hardware |
| Mid-level commands     | Explicit spatial actions            | Interpretable & debuggable |
| Low-level control      | Reactive + simple scoring           | Lightweight, no heavy training |
| Environment            | Real maps via Folium + OSM          | More realistic than pure grid worlds |
| Buildings vs Roads     | OSM semantic tags                   | Proper obstacle vs traversable distinction |

---

## Features

- Hierarchical NaVILA-style command flow
- Multi-command natural language input
- Long-distance movement support
- `return to start / go back` command
- OpenStreetMap integration:
  - `building=*` treated as hard obstacles
  - `highway=*` visualized as preferred paths
- Dynamic map data loading (with timeout safety)
- Multiple map layers (OSM, Light, Dark, Satellite)
- Safe spawn logic
- Interactive Streamlit demo
- Clear separation of planner and controller

---

## How to Run

```bash
git clone https://github.com/ar-shenoy/navila-inspired-navigation.git
cd navila-inspired-navigation
pip install -r requirements_map.txt
streamlit run app_map.py
```

**Recommended first test:**
1. Leave “Load OSM” unchecked (fastest)
2. Click Reset
3. Enter: `Move forward 80 meters then turn left 90 degrees then move 50 meters`
4. Press Execute

---

## Project Structure

```text
navila-inspired-navigation/
├── app_map.py              # Main Streamlit application
├── README.md
├── requirements_map.txt
├── docs/
│   ├── architecture.md
│   ├── navila_analysis.md
│   └── limitations.md
└── src/                    # (modular code can be further split here)
```

---

## Limitations (Honest)

- The high-level planner is currently heuristic-dominant for reliability. A lightweight VLM can be plugged in but is not required for the core demo.
- Building/road loading depends on the public Overpass API and can timeout.
- Collision avoidance is reactive, not a full global planner.
- This is not a trained end-to-end VLA model and does not run in Isaac Sim.
- The system prioritizes demonstrability and hierarchical clarity over maximum sim-to-real fidelity.

---

## Future Work

- Plug in a small instruction-tuned VLM for high-level planning
- Improve road-following bias using highway geometries
- Add simple trajectory scoring / lightweight RL fine-tuning
- Export trajectories for evaluation
- Bridge toward Isaac Sim / real robot deployment

---

## Relation to NaVILA

NaVILA showed that mid-level spatial commands are a strong interface between vision-language models and low-level controllers.  
NaVILA-Lite keeps that hierarchical idea and explores how far it can be taken with:

- Real map data
- Limited compute
- Interactive demonstration
- Practical engineering trade-offs

It is intended as a clear, runnable stepping stone rather than a full reproduction of the original research system.

---

## Author

Built as a focused exploration of hierarchical Vision-Language-Action navigation systems under real hardware constraints.

---

**Inspired by:** Cheng et al., *NaVILA: Legged Robot Vision-Language-Action Model for Navigation*, RSS 2025.
