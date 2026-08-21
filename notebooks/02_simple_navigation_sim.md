# 02 – Simple Navigation Simulation

This notebook connects the **High-Level Planner** with a **Low-Level Controller**.

Pipeline:

```text
Language Instruction
        ↓
High-Level Planner  →  Mid-level Command
        ↓
Low-Level Controller →  Robot Movement (simulated)
```

---

## 1. Setup

```python
import math
import numpy as np
import matplotlib.pyplot as plt
from dataclasses import dataclass
from typing import Optional, List, Tuple
import re

%matplotlib inline
```

---

## 2. High-Level Planner (same as before)

```python
@dataclass
class MidLevelCommand:
    action: str
    value: Optional[float] = None
    raw_text: str = ""

    def __str__(self):
        if self.action == "stop":
            return "stop"
        if self.value is not None:
            if "turn" in self.action:
                return f"{self.action.replace('_', ' ')} {self.value:.0f} degrees"
            else:
                return f"{self.action.replace('_', ' ')} {self.value:.2f} meters"
        return self.action.replace("_", " ")


class SimpleLanguagePlanner:
    def __init__(self):
        self.forward_words = ["forward", "ahead", "straight", "go", "move", "walk"]
        self.left_words = ["left"]
        self.right_words = ["right"]
        self.stop_words = ["stop", "halt", "wait"]

    def parse(self, instruction: str) -> MidLevelCommand:
        instruction = instruction.lower().strip()

        if any(w in instruction for w in self.stop_words):
            return MidLevelCommand(action="stop", raw_text=instruction)

        numbers = re.findall(r"(\d+\.?\d*)", instruction)
        value = float(numbers[0]) if numbers else None

        if any(w in instruction for w in self.left_words):
            angle = value if value is not None else 30.0
            return MidLevelCommand(action="turn_left", value=angle, raw_text=instruction)

        if any(w in instruction for w in self.right_words):
            angle = value if value is not None else 30.0
            return MidLevelCommand(action="turn_right", value=angle, raw_text=instruction)

        if any(w in instruction for w in self.forward_words) or value is not None:
            distance = value if value is not None else 0.75
            if distance > 10:
                distance = distance / 100.0
            return MidLevelCommand(action="move_forward", value=distance, raw_text=instruction)

        return MidLevelCommand(action="move_forward", value=0.5, raw_text=instruction)
```

---

## 3. Low-Level Controller

```python
@dataclass
class RobotState:
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0

class SimpleController:
    def __init__(self, max_linear_speed=0.5, max_angular_speed=1.0):
        self.max_linear_speed = max_linear_speed
        self.max_angular_speed = max_angular_speed
        self.state = RobotState()
        self.trajectory = [(0.0, 0.0)]

    def reset(self, x=0.0, y=0.0, yaw=0.0):
        self.state = RobotState(x=x, y=y, yaw=yaw)
        self.trajectory = [(x, y)]

    def execute(self, action: str, value: float = None, dt: float = 0.1):
        action = action.lower()

        if action == "stop":
            return self.state

        if action == "move_forward":
            distance = value if value is not None else 0.5
            steps = max(1, int(distance / (self.max_linear_speed * dt)))
            step_dist = distance / steps
            for _ in range(steps):
                self.state.x += step_dist * math.cos(self.state.yaw)
                self.state.y += step_dist * math.sin(self.state.yaw)
                self.trajectory.append((self.state.x, self.state.y))

        elif action == "turn_left":
            angle_deg = value if value is not None else 30.0
            angle_rad = math.radians(angle_deg)
            steps = max(1, int(abs(angle_rad) / (self.max_angular_speed * dt)))
            step_angle = angle_rad / steps
            for _ in range(steps):
                self.state.yaw += step_angle
                self.state.yaw = (self.state.yaw + math.pi) % (2 * math.pi) - math.pi
                self.trajectory.append((self.state.x, self.state.y))

        elif action == "turn_right":
            angle_deg = value if value is not None else 30.0
            angle_rad = -math.radians(angle_deg)
            steps = max(1, int(abs(angle_rad) / (self.max_angular_speed * dt)))
            step_angle = angle_rad / steps
            for _ in range(steps):
                self.state.yaw += step_angle
                self.state.yaw = (self.state.yaw + math.pi) % (2 * math.pi) - math.pi
                self.trajectory.append((self.state.x, self.state.y))

        return self.state

    def get_trajectory(self):
        return np.array(self.trajectory)
```

---

## 4. Full Hierarchical Demo

```python
planner = SimpleLanguagePlanner()
controller = SimpleController()

# Sequence of language instructions (like a real navigation task)
instructions = [
    "Move forward 1.0 meters",
    "Turn left 90 degrees",
    "Move forward 0.8 meters",
    "Turn right 45 degrees",
    "Move forward 0.5 meters",
    "Stop",
]

print("=== Hierarchical Navigation Demo ===\n")

controller.reset()

for instr in instructions:
    cmd = planner.parse(instr)
    print(f"Instruction : {instr}")
    print(f"Mid-level   : {cmd}")
    
    controller.execute(cmd.action, cmd.value)
    print(f"Robot state : x={controller.state.x:.2f}, y={controller.state.y:.2f}, yaw={math.degrees(controller.state.yaw):.1f}°")
    print("-" * 60)

print("\nFinal position:", controller.state.x, controller.state.y)
```

---

## 5. Visualize Trajectory

```python
traj = controller.get_trajectory()

plt.figure(figsize=(8, 8))
plt.plot(traj[:, 0], traj[:, 1], "b-", linewidth=2, label="Path")
plt.plot(traj[0, 0], traj[0, 1], "go", markersize=12, label="Start")
plt.plot(traj[-1, 0], traj[-1, 1], "ro", markersize=12, label="End")

# Draw orientation at the end
arrow_len = 0.15
plt.arrow(controller.state.x, controller.state.y,
          arrow_len * math.cos(controller.state.yaw),
          arrow_len * math.sin(controller.state.yaw),
          head_width=0.08, color="red")

plt.axis("equal")
plt.grid(True, alpha=0.3)
plt.xlabel("X (meters)")
plt.ylabel("Y (meters)")
plt.title("NaVILA-style Hierarchical Navigation\nLanguage → Mid-level Command → Motion")
plt.legend()
plt.show()
```

---
