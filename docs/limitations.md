# Limitations & Practical Constraints

This document honestly describes what is and is not possible with the current hardware setup.

---

## 1. Hardware Reality

| Component              | Requirement for full NaVILA + Isaac Sim | Available in this project |
|------------------------|-----------------------------------------|---------------------------|
| GPU                    | Strong NVIDIA GPU (ideally ≥ 16–24 GB) | AMD Radeon 6500M / Kaggle T4 |
| Isaac Sim              | Official NVIDIA Isaac Sim / Isaac Lab  | Not runnable on AMD       |
| Full NaVILA weights    | Large VLM + locomotion policy          | Not loaded                |
| Real-time control      | High-frequency locomotion loop         | Simulated / simplified    |

**Conclusion:** Running the complete NaVILA stack (Isaac Sim + full model) is not feasible on the available hardware.

---

## 2. What We Can Still Do Well

Even with these constraints we can still produce a meaningful submission by focusing on:

1. **Deep understanding** of the NaVILA architecture and design choices.
2. **Clear hierarchical design** that mirrors the original paper.
3. **Runnable high-level prototype** (language + vision → mid-level command) that works on Kaggle T4.
4. **Honest discussion** of how the system would connect to Isaac Sim and real robots.
5. **Clean documentation** so a reviewer can quickly see the thought process.

---

## 3. What a Full Implementation Would Require

To run the complete pipeline one would need:

- NVIDIA GPU workstation or cloud instance
- Isaac Sim / Isaac Lab installation
- NaVILA model weights and locomotion policies
- Proper ROS 2 / Isaac bridge for real robot deployment

This is left as future work once suitable hardware is available.

---

## 4. Design Decision

Given the constraints, this repository prioritizes:

- Clarity of ideas over complete system execution
- Hierarchical design fidelity to NaVILA
- Reproducibility on free / limited compute (Kaggle)

This approach still demonstrates the core technical understanding required for the exploration task proposed by Hucenrotia Laboratory.
