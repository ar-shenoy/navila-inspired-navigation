# NaVILA-Inspired Language-Guided Navigation

A simplified yet structured exploration of **Vision-Language-Action (VLA)** models for robot navigation, inspired by [NaVILA](https://navila-bot.github.io/) (RSS 2025).

This repository demonstrates understanding of hierarchical VLA + locomotion architectures and provides runnable prototypes that can run on limited hardware (Kaggle T4 / consumer GPUs).

---

## Motivation

NaVILA proposes a clean two-level framework for legged robot navigation:

- **High-level**: A Vision-Language model that takes RGB observations + language instructions and outputs **mid-level spatial commands** (e.g. “move forward 75cm”, “turn left”).
- **Low-level**: A visual locomotion policy that executes these commands while handling obstacle avoidance and balance.

Directly predicting low-level joint actions from a VLA is difficult. NaVILA’s hierarchical design makes the system more generalizable and easier to transfer across robots.

This project aims to:
1. Deeply understand and document the NaVILA architecture
2. Implement a simplified high-level language planner
3. Show how such a system can be connected to a low-level controller
4. Discuss practical limitations when running on limited hardware (no Isaac Sim GPU)

---

## Repository Structure

```text
navila-inspired-navigation/
├── README.md
├── docs/
│   ├── architecture.md          # Detailed system design
│   ├── navila_analysis.md       # Paper analysis
│   └── limitations.md           # Hardware & practical constraints
├── notebooks/
│   ├── 01_vla_concept_demo.ipynb
│   └── 02_simple_navigation_sim.ipynb
├── src/
│   ├── high_level/
│   │   └── language_planner.py
│   ├── low_level/
│   │   └── simple_controller.py
│   └── utils/
├── assets/
│   └── diagrams/
├── requirements.txt
└── .gitignore
