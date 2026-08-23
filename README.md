# NaVILA-Lite

**Practical hierarchical Vision-Language Navigation on real maps**

Inspired by [NaVILA (RSS 2025)](https://navila-bot.github.io/).  
This project keeps the core hierarchical idea — **high-level language → mid-level spatial commands → low-level control** — while running on limited consumer hardware **without NVIDIA Isaac Sim**.

> **Run this:** `streamlit run app_map_v2.py`  
> Older files (`app.py`, `app_map.py`) are legacy experiments only.

---

## Motivation

Full NaVILA-style systems usually need Isaac Sim and strong NVIDIA GPUs.  
This prototype was built under real constraints (AMD laptop / limited GPU, no Isaac access) to still demonstrate:

- understanding of hierarchical VLN / VLA design
- a working end-to-end demo on **real map data**
- honest engineering trade-offs when full sim-to-real is not available

---

## Quick start

```bash
git clone https://github.com/ar-shenoy/navila-inspired-navigation.git
cd navila-inspired-navigation
pip install -r requirements_map.txt
streamlit run app_map_v2.py
```

**Suggested demo**

1. Leave “Live OSM scan expand” **off** (fastest)
2. Start location: Taipei 101
3. Language: `Move forward 70 meters then turn left 90 degrees then move 40 meters` → **Execute Language**
4. Landmark: `Taipei Main Station` → **Execute Landmark**

Optional VLM: set `HF_TOKEN` in the environment or Streamlit secrets. The system works without it.

---

## Architecture (current)

```text
Language instruction  OR  landmark name
              │
              ▼
┌──────────────────────────────────────┐
│ High-level planner                   │
│  • hybrid heuristic (default)        │
│  • optional lightweight VLM          │
│  • map-context summary               │
└──────────────────────────────────────┘
              │ mid-level commands
              ▼
┌──────────────────────────────────────┐
│ Low-level controller                 │
│  • heading-aware motion              │
│  • local building avoidance          │
│  • full OSRM waypoint following      │
└──────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────┐
│ Real map layer                       │
│  • OSRM public routing (road paths)  │
│  • prebaked local buildings          │
│  • optional live OSM expand          │
└──────────────────────────────────────┘
```

More detail: [`docs/architecture.md`](docs/architecture.md)

---

## Features

- Hierarchical NaVILA-style command flow
- Multi-command natural language instructions
- Landmark navigation (Nominatim + **OSRM** real-road routes)
- Instant **prebaked** obstacles for listed spawn maps
- Optional live OSM expand while moving (off by default)
- Separate Execute buttons (Landmark vs Language)
- Movement score, collisions, explainability panel
- Modular `src/` layout

---

## Repository layout

```text
app_map_v2.py              ← main app (use this)
requirements_map.txt
data/preloaded/            ← instant obstacle packs
src/
  high_level/              ← planner, geocoder, OSRM router
  low_level/               ← motion + avoidance + route following
  map/                     ← prebaked + optional live OSM
docs/                      ← architecture, limitations, future work
notebooks/                 ← early concept experiments (not required to run the app)
```

---

## Limitations (honest)

- Not a full trained VLA and not an Isaac Sim deployment
- Planner is heuristic-dominant by default; VLM is optional
- Continuous city-scale live OSM obstacle streaming is limited by public Overpass latency → addressed with prebaked packs + OSRM roads
- Collision checks are geometric
- Long-distance travel follows OSRM roads; dense local avoidance is strongest near prebaked/expanded regions

Full write-up: [`docs/limitations.md`](docs/limitations.md)

---

## What we could do next

Documented roadmap (not claimed as done):

1. **Stronger structured command generation** — constrained JSON / better prompts so optional VLM outputs are more reliable  
2. **Simple evaluation harness** — success rate, path efficiency, collision rate on fixed start→goal pairs  
3. **Shareable demo host** — e.g. Hugging Face Spaces  
4. **Richer local perception** — only if compute allows (small open VLMs, better map context)  
5. **Bridge to full sim** — Isaac Sim / Habitat-style stack when NVIDIA GPU access is available  
6. **Optional fine-tuning path** — small open VLM on navigation-style instruction data (research direction)

Details: [`docs/future_work.md`](docs/future_work.md)

---

## Inspiration

Cheng et al., *NaVILA: Legged Robot Vision-Language-Action Model for Navigation*, RSS 2025.

This repository is an independent practical exploration of hierarchical VLN ideas under hardware constraints, not an official NaVILA implementation.
