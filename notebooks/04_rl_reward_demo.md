# 04 – RL-Inspired Low-Level Controller with Explicit Reward

This notebook upgrades the low-level part of NaVILA-Lite with:

- A clear **reward function**
- A reactive policy that chooses actions to maximize immediate reward
- Obstacle avoidance driven by the reward signal

This follows common practice in navigation RL while remaining lightweight.

---

## 1. Setup

```python
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict

%matplotlib inline
```

---

## 2. Reward Function & RL-Inspired Controller

(Copy the classes `RewardCalculator` and `RLInspiredController` from `src/low_level/rl_controller.py` here, or import them if you have the file.)

For convenience the full code is also available in the repository.

---

## 3. Quick Test

```python
# After pasting the controller classes...

controller = RLInspiredController(world_size=8.0)
controller.reset(x=1.0, y=1.0, yaw=0.0)

# Cluttered environment
obstacles = [
    (2.5, 2.5, 0.5),
    (4.0, 5.0, 0.55),
    (5.5, 2.2, 0.45),
    (3.0, 6.0, 0.5),
]
controller.set_obstacles(obstacles)

print("Initial total reward:", controller.get_total_reward())

# Execute a forward command
result = controller.execute(action="move_forward", value=1.5)
print("Command reward:", round(result.reward, 3))
print("Total reward:", round(controller.get_total_reward(), 3))
print("Final position:", round(controller.state.x, 2), round(controller.state.y, 2))
print("Collision:", result.collision)
```

---

## 4. Visualization with Reward

```python
def draw_with_reward(controller, title=""):
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.set_xlim(0, controller.world_size)
    ax.set_ylim(0, controller.world_size)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)

    for ox, oy, r in controller.obstacles:
        ax.add_patch(Circle((ox, oy), r, color="#e74c3c", alpha=0.75))

    if len(controller.trajectory) > 1:
        traj = np.array(controller.trajectory)
        ax.plot(traj[:, 0], traj[:, 1], "b-", lw=2)

    ax.add_patch(Circle((controller.state.x, controller.state.y), 0.25, color="#2ecc71", zorder=5))
    ax.arrow(
        controller.state.x, controller.state.y,
        0.4 * math.cos(controller.state.yaw),
        0.4 * math.sin(controller.state.yaw),
        head_width=0.15, color="#27ae60", zorder=6
    )

    ax.set_title(title or f"Total Reward: {controller.get_total_reward():.2f}")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    plt.show()

draw_with_reward(controller, title=f"After move_forward | Total Reward: {controller.get_total_reward():.2f}")
```

---

## Key Points

- We now have an **explicit reward function** (progress, collision penalty, time penalty, success bonus).
- The controller selects actions that maximize immediate reward (greedy reactive policy).
- This is a standard lightweight approach used in many navigation papers when full RL training is too expensive.

Next we will connect this improved low-level module with a stronger high-level AI component.
