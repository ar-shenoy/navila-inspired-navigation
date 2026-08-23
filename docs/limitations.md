# Limitations & Practical Constraints

Honest description of what this project is and is not.

---

## 1. Hardware reality

| Component | Typical full NaVILA + Isaac path | This project |
|-----------|----------------------------------|--------------|
| GPU | Strong NVIDIA GPU | AMD laptop / limited GPU; optional Kaggle T4 |
| Isaac Sim | Required for official stack | Not available on AMD setup |
| Full NaVILA weights | Large VLA + locomotion policy | Not loaded |
| Environment | Photorealistic sim + robot | Real map demo (OSM + OSRM + Streamlit) |

**Conclusion:** The complete NaVILA + Isaac Sim pipeline was not runnable on the available machine. The project focuses on the hierarchical idea and a demonstrable map-grounded prototype instead.

---

## 2. What works well here

- Clear hierarchical interface (language/landmark → mid-level → low-level)
- Interactive demo on real city maps
- Landmark routing via open-source OSRM
- Instant prebaked local obstacles for reliable demos
- Explainability and basic scoring
- Runs on consumer hardware

---

## 3. Known technical limits

1. **High-level planner**  
   Default path is a strong heuristic. Optional VLM depends on network/API availability and is not a fully trained navigation VLA.

2. **Live dense OSM obstacles**  
   Continuous Overpass/OSMnx queries are slow and can timeout. That is why prebaked packs are the default and live expand is optional.

3. **Collision model**  
   Geometric building polygons, not full semantic 3D perception.

4. **Long-horizon routes**  
   Primarily follow OSRM road geometry. Local avoidance is strongest near prebaked/expanded regions.

5. **Not a benchmarked VLN agent**  
   No claim of R2R/RxR SOTA metrics in the current demo.

---

## 4. Design decision

Given the constraints, this repository prioritizes:

- hierarchical design fidelity to the NaVILA *idea*
- a working, shareable demo
- reproducibility on limited compute
- honest documentation of trade-offs

This is intended to show technical understanding and implementation seriousness for exploration / internship discussion — not to claim a full reproduction of the NaVILA system.
