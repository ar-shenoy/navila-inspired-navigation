# 05 – Full Pipeline: AI High-Level + RL Low-Level

End-to-end hierarchical navigation:

Language → AI High-Level Planner → Mid-level Command → RL-Inspired Controller → Motion + Reward

---

## Setup

```python
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
import re

%matplotlib inline
```

## Instructions

1. Copy the `AIHighLevelPlanner` class from `src/high_level/ai_planner.py`
2. Copy the `RewardCalculator` + `RLInspiredController` from `src/low_level/rl_controller.py`
3. Run the full pipeline below.

## Full Demo

```python
planner = AIHighLevelPlanner()
controller = RLInspiredController(world_size=8.0)

obstacles = [
    (2.8, 2.5, 0.5),
    (4.5, 5.0, 0.55),
    (6.0, 2.8, 0.45),
    (3.5, 6.2, 0.5),
]
controller.reset(x=1.0, y=1.0, yaw=0.0)
controller.set_obstacles(obstacles)

instructions = [
    "Move forward 1.3 meters",
    "Turn left 60 degrees",
    "Go straight 0.9 meters",
    "Turn right 30 degrees",
    "Move forward carefully 0.7 meters",
    "Stop",
]

print("=== Full Hierarchical Pipeline (AI + RL) ===\n")

for instr in instructions:
    cmd = planner.parse(instr)
    result = controller.execute(cmd.action, cmd.value)

    print(f"Instruction : {instr}")
    print(f"Mid-level   : {cmd}  [{cmd.source}]")
    print(f"Reward      : {result.reward:.3f}  |  Total: {controller.get_total_reward():.3f}")
    print(f"State       : x={controller.state.x:.2f}, y={controller.state.y:.2f}, yaw={math.degrees(controller.state.yaw):.1f}°")
    print(f"Collision   : {result.collision}")
    print("-" * 60)

print("\nFinal Total Reward:", round(controller.get_total_reward(), 3))
```

## Visualization

```python
def draw_final(controller, title=""):
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_xlim(0, controller.world_size)
    ax.set_ylim(0, controller.world_size)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)

    for ox, oy, r in controller.obstacles:
        ax.add_patch(Circle((ox, oy), r, color="#e74c3c", alpha=0.75))

    if len(controller.trajectory) > 1:
        traj = np.array(controller.trajectory)
        ax.plot(traj[:, 0], traj[:, 1], "b-", lw=2.5, label="Path")

    ax.add_patch(Circle((controller.state.x, controller.state.y), 0.25, color="#2ecc71", zorder=5))
    ax.arrow(controller.state.x, controller.state.y,
             0.45 * math.cos(controller.state.yaw),
             0.45 * math.sin(controller.state.yaw),
             head_width=0.16, color="#27ae60", zorder=6)

    ax.set_title(title or f"Total Reward: {controller.get_total_reward():.2f}")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.legend()
    plt.show()

draw_final(controller)
```
