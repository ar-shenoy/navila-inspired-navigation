# NaVILA-Lite – Interactive Kaggle Demo

Hierarchical Vision-Language Navigation inspired by NaVILA (RSS 2025).

This notebook runs fully on Kaggle (CPU or T4).

**Pipeline:**
Language Instruction → High-Level Planner → Mid-level Command → Low-Level Controller (with reactive avoidance) → Visualization

---

## 1. Setup

```python
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional
import re
from IPython.display import display, clear_output
import ipywidgets as widgets

%matplotlib inline
plt.rcParams["figure.figsize"] = (7, 7)
```

---

## 2. Core Classes

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
                return f"{self.action.replace('_', ' ')} {self.value:.0f}°"
            return f"{self.action.replace('_', ' ')} {self.value:.2f}m"
        return self.action.replace("_", " ")


@dataclass
class RobotState:
    x: float = 1.0
    y: float = 1.0
    yaw: float = 0.0


class HighLevelPlanner:
    def __init__(self):
        self.forward_words = ["forward", "ahead", "straight", "go", "move", "walk", "advance"]
        self.left_words = ["left"]
        self.right_words = ["right"]
        self.stop_words = ["stop", "halt", "wait", "stay"]

    def parse(self, instruction: str) -> MidLevelCommand:
        text = instruction.lower().strip()

        if any(w in text for w in self.stop_words):
            return MidLevelCommand("stop", raw_text=instruction)

        numbers = re.findall(r"(\d+\.?\d*)", text)
        value = float(numbers[0]) if numbers else None

        if any(w in text for w in self.left_words):
            angle = value if value is not None else 30.0
            return MidLevelCommand("turn_left", angle, instruction)

        if any(w in text for w in self.right_words):
            angle = value if value is not None else 30.0
            return MidLevelCommand("turn_right", angle, instruction)

        distance = value if value is not None else 0.6
        if distance > 5:
            distance /= 100.0
        return MidLevelCommand("move_forward", distance, instruction)


class LowLevelController:
    def __init__(self, world_size=8.0):
        self.world_size = world_size
        self.state = RobotState()
        self.trajectory: List[Tuple[float, float]] = []
        self.obstacles: List[Tuple[float, float, float]] = []

    def reset(self, x=1.0, y=1.0, yaw=0.0):
        self.state = RobotState(x=x, y=y, yaw=yaw)
        self.trajectory = [(x, y)]

    def set_obstacles(self, obstacles):
        self.obstacles = obstacles

    def _is_collision(self, x, y, robot_radius=0.25):
        for ox, oy, r in self.obstacles:
            if math.hypot(x - ox, y - oy) < (r + robot_radius):
                return True
        if x < 0.3 or y < 0.3 or x > self.world_size - 0.3 or y > self.world_size - 0.3:
            return True
        return False

    def execute(self, cmd: MidLevelCommand, steps=25):
        if cmd.action == "stop":
            return self.state

        if cmd.action == "move_forward":
            distance = cmd.value if cmd.value else 0.6
            step_size = distance / steps

            for _ in range(steps):
                nx = self.state.x + step_size * math.cos(self.state.yaw)
                ny = self.state.y + step_size * math.sin(self.state.yaw)

                if self._is_collision(nx, ny):
                    # Reactive (RL-inspired) avoidance
                    turned = False
                    for delta in [0.35, -0.35, 0.7, -0.7, 1.0, -1.0]:
                        test_yaw = self.state.yaw + delta
                        tx = self.state.x + step_size * math.cos(test_yaw)
                        ty = self.state.y + step_size * math.sin(test_yaw)
                        if not self._is_collision(tx, ty):
                            self.state.yaw = test_yaw
                            self.state.x, self.state.y = tx, ty
                            turned = True
                            break
                    if not turned:
                        break
                else:
                    self.state.x, self.state.y = nx, ny

                self.trajectory.append((self.state.x, self.state.y))

        elif cmd.action in ["turn_left", "turn_right"]:
            angle_deg = cmd.value if cmd.value else 30.0
            angle_rad = math.radians(angle_deg)
            if cmd.action == "turn_right":
                angle_rad = -angle_rad
            self.state.yaw += angle_rad
            self.state.yaw = (self.state.yaw + math.pi) % (2 * math.pi) - math.pi
            self.trajectory.append((self.state.x, self.state.y))

        return self.state
```

---

## 3. Environments

```python
def get_environment(name: str):
    if name == "Empty Room":
        return []
    elif name == "Corridor":
        return [(2.0, 3.5, 0.55), (4.2, 1.8, 0.5), (6.0, 4.2, 0.6)]
    elif name == "Cluttered":
        return [(2.5, 2.5, 0.5), (4.0, 5.2, 0.55), (5.8, 2.2, 0.45),
                (3.2, 6.0, 0.5), (6.5, 5.5, 0.5)]
    return []
```

---

## 4. Visualization

```python
def draw_world(controller, title=""):
    fig, ax = plt.subplots()
    ax.set_xlim(0, controller.world_size)
    ax.set_ylim(0, controller.world_size)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    ax.set_title(title or "NaVILA-Lite")

    for ox, oy, r in controller.obstacles:
        ax.add_patch(Circle((ox, oy), r, color="#e74c3c", alpha=0.75))

    if len(controller.trajectory) > 1:
        traj = np.array(controller.trajectory)
        ax.plot(traj[:, 0], traj[:, 1], "b-", lw=2, alpha=0.85)

    ax.add_patch(Circle((controller.state.x, controller.state.y), 0.25, color="#2ecc71", zorder=5))
    arrow_len = 0.4
    ax.arrow(controller.state.x, controller.state.y,
             arrow_len * math.cos(controller.state.yaw),
             arrow_len * math.sin(controller.state.yaw),
             head_width=0.15, color="#27ae60", zorder=6)

    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    plt.show()
```

---

## 5. Interactive Demo

```python
planner = HighLevelPlanner()
controller = LowLevelController()
controller.reset()
controller.set_obstacles(get_environment("Corridor"))
history = []

def run_command(instruction, env_name):
    global history
    controller.set_obstacles(get_environment(env_name))
    cmd = planner.parse(instruction)
    controller.execute(cmd)
    history.append({
        "instruction": instruction,
        "mid_level": str(cmd),
        "x": round(controller.state.x, 2),
        "y": round(controller.state.y, 2),
        "yaw": round(math.degrees(controller.state.yaw), 1)
    })
    clear_output(wait=True)
    print(f"Instruction : {instruction}")
    print(f"Mid-level   : {cmd}")
    print(f"Robot state : x={controller.state.x:.2f}, y={controller.state.y:.2f}, yaw={math.degrees(controller.state.yaw):.1f}°")
    print("-" * 50)
    draw_world(controller, title=f"Environment: {env_name}")

def reset_sim(env_name):
    global history
    controller.reset()
    controller.set_obstacles(get_environment(env_name))
    history = []
    clear_output(wait=True)
    print("Simulation reset.")
    draw_world(controller, title=f"Environment: {env_name}")

# Widgets
env_dropdown = widgets.Dropdown(
    options=["Empty Room", "Corridor", "Cluttered"],
    value="Corridor",
    description="Environment:"
)

instr_input = widgets.Text(
    value="Move forward 1.0 meters",
    description="Instruction:",
    layout=widgets.Layout(width="500px")
)

run_button = widgets.Button(description="Execute", button_style="success")
reset_button = widgets.Button(description="Reset", button_style="warning")

def on_run(b):
    run_command(instr_input.value, env_dropdown.value)

def on_reset(b):
    reset_sim(env_dropdown.value)

run_button.on_click(on_run)
reset_button.on_click(on_reset)

display(env_dropdown, instr_input, widgets.HBox([run_button, reset_button]))
print("\nReady. Choose environment, type instruction, and click Execute.")
draw_world(controller, title="Environment: Corridor")
```

---

## 6. Example Commands to try

```text
Move forward 1.2 meters
Turn left 90 degrees
Move forward 0.8 meters
Turn right 45 degrees
Stop
Go straight
```

---

## Summary

This notebook demonstrates the full hierarchical idea of NaVILA in a form that runs entirely on Kaggle:

- High-level planner converts language → mid-level commands
- Low-level controller executes them with reactive obstacle avoidance
- Multiple environments
- Interactive controls + live visualization
