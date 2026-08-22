# NaVILA-Lite

**Hierarchical Vision-Language Navigation Demo**  
Inspired by [NaVILA (RSS 2025)](https://navila-bot.github.io/)

A lightweight, end-to-end hierarchical navigation system that separates high-level language reasoning from low-level reactive control.

---

## Key Idea (from NaVILA)

Instead of predicting low-level actions directly from a Vision-Language model, NaVILA uses a clean two-level design:

1. **High-level** → Vision-Language model outputs mid-level spatial commands  
   (`move_forward 0.8`, `turn_left 30`, `stop`, ...)
2. **Low-level** → A reactive / RL-inspired controller executes these commands while handling obstacles.

This project implements a practical, runnable version of that idea that works on limited hardware (Kaggle T4 / free-tier resources).

---

## Features

- Hybrid High-Level Planner
  - Tries a real lightweight VLM (SmolVLM)
  - Automatically falls back to a strong heuristic when the VLM output is unreliable
- Low-Level Controller with explicit reward function (progress, collision penalty, time penalty, success bonus)
- Reactive obstacle avoidance
- Multiple environments
- Interactive demo (user can type instructions)
- Clean visualization of the robot trajectory and state

---

## Project Structure

```text
navila-inspired-navigation/
├── README.md
├── docs/
│   ├── architecture.md
│   ├── navila_analysis.md
│   └── limitations.md
├── src/
│   ├── high_level/
│   │   ├── vlm_planner.py          # Hybrid VLM + heuristic planner
│   │   └── ...
│   ├── low_level/
│   │   └── rl_controller.py        # Reward-based reactive controller
│   └── visualization/
├── notebooks/
│   └── final_demo.ipynb            # Main interactive demo
└── requirements.txt
```

---

## How to Run (Kaggle)

1. Open the final demo notebook
2. Run all cells
3. Type natural language instructions and execute them
4. Watch the robot navigate while avoiding obstacles

The system will show:
- Which planner was used (`vlm` or `heuristic`)
- Mid-level command generated
- Reward obtained
- Current robot state

---

## Design Decisions

| Component              | Choice                              | Reason |
|------------------------|-------------------------------------|--------|
| High-level             | Hybrid (SmolVLM + heuristic)        | Real VLM when possible + robustness |
| Low-level              | Explicit reward + reactive policy   | Lightweight, interpretable, no heavy training |
| Simulation             | Top-down / 3D visualization         | Runs easily on free compute |
| Hardware target        | Kaggle T4 / free HF Spaces          | Accessible |

---

## Limitations

- The small VLM (SmolVLM-500M) is not perfectly reliable for structured navigation commands → hybrid fallback is necessary.
- Full physics 3D simulation (Isaac Sim style) is not feasible on free-tier hardware.
- This is a research-oriented prototype demonstrating the hierarchical idea, not a production robot stack.

See `docs/limitations.md` for more details.

---

## Future Work

- Better fine-tuned small VLM for navigation commands
- Stronger low-level policy (learned)
- Proper 3D web visualization (Three.js)
- Integration path toward Isaac Sim / real robots

---

## References

- Cheng et al., **NaVILA: Legged Robot Vision-Language-Action Model for Navigation**, RSS 2025  
  https://navila-bot.github.io/
- SmolVLM (Hugging Face)

---

## Author

Built as an exploration project for hierarchical Vision-Language-Action navigation systems.
