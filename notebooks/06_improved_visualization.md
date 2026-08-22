# 06 – Improved Visualization + Full Pipeline

Better looking top-down rendering for the hierarchical navigation demo.

---

## Setup

```python
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, Polygon
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
import re

%matplotlib inline
```

## Load the modules

Copy into the notebook:

- `AIHighLevelPlanner` (from `src/high_level/ai_planner.py`)
- `RLInspiredController` + `RewardCalculator` (from `src/low_level/rl_controller.py`)
- `render_world` + `create_robot_patch` (from `src/visualization/renderer.py`)

---

## Run Full Pipeline with Better Visualization

```python
planner = AIHighLevelPlanner()
controller = RLInspiredController(world_size=8.0)

obstacles = [
    (2.8, 2.5, 0.5),
    (4.5, 5.0, 0.55),
    (6.0, 2.8, 0.45),
    (3.5, 6.2, 0.5),
    (5.5, 4.0, 0.4),
]
controller.reset(x=1.0, y=1.0, yaw=0.0)
controller.set_obstacles(obstacles)

instructions = [
    "Move forward 1.4 meters",
    "Turn left 55 degrees",
    "Go straight 1.0 meters",
    "Turn right 40 degrees",
    "Move forward carefully 0.8 meters",
    "Stop",
]

print("=== NaVILA-Lite | AI + RL Pipeline ===\n")

for instr in instructions:
    cmd = planner.parse(instr)
    result = controller.execute(cmd.action, cmd.value)

    print(f"Instruction : {instr}")
    print(f"Mid-level   : {cmd}  [{cmd.source}]")
    print(f"Reward      : {result.reward:.3f}  |  Total: {controller.get_total_reward():.3f}")
    print(f"Collision   : {result.collision}")
    print("-" * 55)

print("\nFinal Total Reward:", round(controller.get_total_reward(), 3))
```

## Render

```python
fig = render_world(
    trajectory=controller.trajectory,
    robot_state=controller.state,
    obstacles=controller.obstacles,
    world_size=controller.world_size,
    total_reward=controller.get_total_reward(),
    title="NaVILA-Lite  |  AI High-Level + RL Low-Level"
)
plt.show()
```
