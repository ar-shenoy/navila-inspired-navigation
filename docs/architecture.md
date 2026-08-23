# System Architecture

This document describes the **current** architecture of NaVILA-Lite (the Streamlit map demo).

It is inspired by NaVILA’s hierarchical design, adapted for limited hardware and real map data.

---

## Overview

```text
Language instruction  OR  landmark name
              │
              ▼
┌──────────────────────────────────────┐
│ High-level planner                   │
│  src/high_level/vlm_planner.py       │
│  • hybrid heuristic (default)        │
│  • optional lightweight VLM          │
│  • map-context string                │
└──────────────────────────────────────┘
              │ mid-level commands
              │ (move_forward, turn_*, stop, return_home, ...)
              ▼
┌──────────────────────────────────────┐
│ Low-level controller                 │
│  src/low_level/osm_controller.py     │
│  • heading-aware steps               │
│  • local building collision checks   │
│  • follow_waypoints for full routes  │
└──────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────┐
│ Map / routing layer                  │
│  • OSRM (src/high_level/router.py)   │
│  • Nominatim geocoder                │
│  • prebaked buildings (data/)        │
│  • optional live OSM expand          │
└──────────────────────────────────────┘
```

**Main entry point:** `app_map_v2.py`

---

## 1. High-level module (`src/high_level/`)

**Role:** turn language (and optional map context) into mid-level spatial commands.

| File | Role |
|------|------|
| `vlm_planner.py` | Hybrid planner: heuristic parsing + optional HF VLM |
| `geocoder.py` | Landmark → lat/lon (Nominatim) |
| `router.py` | Start/goal → road waypoints (public OSRM) |

Mid-level actions used in the demo include:

- `move_forward` (meters)
- `turn_left` / `turn_right` (degrees)
- `stop`
- `return_home`

In full NaVILA, the high-level stage is a large vision-language-action model conditioned on robot camera history.  
Here, “vision” is approximated by **map context** (nearby buildings/roads summary + real road routes), which is a deliberate hardware-driven simplification.

---

## 2. Low-level module (`src/low_level/`)

**Role:** execute mid-level commands safely on the map.

`osm_controller.py` provides:

- heading-aware movement (yaw 0 = North)
- geometric collision checks against building polygons
- reactive avoidance / stuck recovery
- `follow_waypoints()` for completing OSRM routes in one execution
- simple movement score (progress vs collisions)

In full NaVILA, low-level control is a learned locomotion policy in simulation.  
Here it is a transparent kinematic controller so the hierarchical interface stays clear and runnable.

---

## 3. Map layer (`src/map/` + `data/preloaded/`)

| Mechanism | Purpose |
|-----------|---------|
| Prebaked obstacle packs | Instant local buildings for demo spawns (no Overpass wait) |
| Optional live OSM expand | Fetch more buildings while moving (&lt;100 m style scan) |
| OSRM public API | Real road geometry for landmark navigation |

This combination keeps the interactive demo responsive while still using open map data.

---

## 4. Design principles

1. **Hierarchy over end-to-end** — mid-level commands remain the interface
2. **Separation of concerns** — planning vs execution vs map data
3. **Runnable on limited hardware** — no Isaac Sim required
4. **Honesty** — document what is simplified vs a full VLA stack

---

## 5. Legacy files (do not confuse)

| Path | Status |
|------|--------|
| `app_map_v2.py` | **Current main app** |
| `app_map.py`, `app.py` | Older prototypes |
| `notebooks/` | Early concept experiments |

Always start from `app_map_v2.py`.
