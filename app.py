"""
NaVILA-Lite: Interactive Hierarchical Vision-Language Navigation Demo
Single Streamlit application
"""

import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, FancyArrowPatch
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional
import time

# -------------------------------------------------
# Data structures
# -------------------------------------------------
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
    x: float = 0.5
    y: float = 0.5
    yaw: float = 0.0  # radians


# -------------------------------------------------
# High-Level Planner (improved)
# -------------------------------------------------
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

        import re
        numbers = re.findall(r"(\d+\.?\d*)", text)
        value = float(numbers[0]) if numbers else None

        if any(w in text for w in self.left_words):
            angle = value if value is not None else 30.0
            return MidLevelCommand("turn_left", angle, instruction)

        if any(w in text for w in self.right_words):
            angle = value if value is not None else 30.0
            return MidLevelCommand("turn_right", angle, instruction)

        # Default to move forward
        distance = value if value is not None else 0.6
        if distance > 5:  # treat as cm
            distance /= 100.0
        return MidLevelCommand("move_forward", distance, instruction)


# -------------------------------------------------
# Low-Level Controller with simple RL-inspired avoidance
# -------------------------------------------------
class LowLevelController:
    def __init__(self, world_size=8.0):
        self.world_size = world_size
        self.state = RobotState()
        self.trajectory: List[Tuple[float, float]] = []
        self.obstacles: List[Tuple[float, float, float]] = []  # x, y, radius

    def reset(self, x=1.0, y=1.0, yaw=0.0):
        self.state = RobotState(x=x, y=y, yaw=yaw)
        self.trajectory = [(x, y)]

    def set_obstacles(self, obstacles):
        self.obstacles = obstacles

    def _is_collision(self, x, y, robot_radius=0.25):
        for ox, oy, r in self.obstacles:
            if math.hypot(x - ox, y - oy) < (r + robot_radius):
                return True
        # World boundary
        if x < 0.3 or y < 0.3 or x > self.world_size - 0.3 or y > self.world_size - 0.3:
            return True
        return False

    def execute(self, cmd: MidLevelCommand, steps=20):
        """Execute mid-level command with simple reactive avoidance."""
        if cmd.action == "stop":
            return self.state

        if cmd.action == "move_forward":
            distance = cmd.value if cmd.value else 0.6
            step_size = distance / steps

            for _ in range(steps):
                nx = self.state.x + step_size * math.cos(self.state.yaw)
                ny = self.state.y + step_size * math.sin(self.state.yaw)

                if self._is_collision(nx, ny):
                    # Simple RL-inspired reactive behavior: try small turns
                    turned = False
                    for delta in [0.4, -0.4, 0.8, -0.8]:
                        test_yaw = self.state.yaw + delta
                        tx = self.state.x + step_size * math.cos(test_yaw)
                        ty = self.state.y + step_size * math.sin(test_yaw)
                        if not self._is_collision(tx, ty):
                            self.state.yaw = test_yaw
                            self.state.x = tx
                            self.state.y = ty
                            turned = True
                            break
                    if not turned:
                        break  # stuck
                else:
                    self.state.x = nx
                    self.state.y = ny

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


# -------------------------------------------------
# Environments
# -------------------------------------------------
def get_environment(name: str):
    if name == "Empty Room":
        return []
    elif name == "Corridor":
        return [
            (2.0, 3.5, 0.6),
            (4.0, 1.5, 0.5),
            (6.0, 4.0, 0.7),
        ]
    elif name == "Cluttered":
        return [
            (2.5, 2.5, 0.5),
            (4.0, 5.0, 0.6),
            (5.5, 2.0, 0.45),
            (3.0, 6.0, 0.55),
            (6.5, 5.5, 0.5),
        ]
    return []


# -------------------------------------------------
# Visualization
# -------------------------------------------------
def draw_world(controller: LowLevelController, title=""):
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.set_xlim(0, controller.world_size)
    ax.set_ylim(0, controller.world_size)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_title(title or "NaVILA-Lite Simulation")

    # Obstacles
    for ox, oy, r in controller.obstacles:
        circle = Circle((ox, oy), r, color="#e74c3c", alpha=0.7)
        ax.add_patch(circle)

    # Trajectory
    if len(controller.trajectory) > 1:
        traj = np.array(controller.trajectory)
        ax.plot(traj[:, 0], traj[:, 1], "b-", linewidth=2, alpha=0.8, label="Path")

    # Robot
    robot = Circle((controller.state.x, controller.state.y), 0.25, color="#2ecc71", zorder=5)
    ax.add_patch(robot)

    # Heading arrow
    arrow_len = 0.4
    ax.arrow(
        controller.state.x, controller.state.y,
        arrow_len * math.cos(controller.state.yaw),
        arrow_len * math.sin(controller.state.yaw),
        head_width=0.15, color="#27ae60", zorder=6
    )

    ax.legend(loc="upper right")
    return fig


# -------------------------------------------------
# Streamlit UI
# -------------------------------------------------
st.set_page_config(page_title="NaVILA-Lite", page_icon="🤖", layout="wide")

st.title("🤖 NaVILA-Lite")
st.markdown("**Hierarchical Vision-Language Navigation Demo** (inspired by NaVILA)")

st.markdown("""
This demo follows the NaVILA two-level design:
- **High-level**: Language → mid-level spatial commands
- **Low-level**: Controller + reactive (RL-inspired) obstacle avoidance
""")

# Sidebar
with st.sidebar:
    st.header("Controls")
    env_name = st.selectbox("Environment", ["Empty Room", "Corridor", "Cluttered"])
    instruction = st.text_input("Language Instruction", value="Move forward 1.2 meters")
    col1, col2 = st.columns(2)
    run_btn = col1.button("Execute", type="primary")
    reset_btn = col2.button("Reset")

# Session state
if "controller" not in st.session_state:
    st.session_state.controller = LowLevelController()
    st.session_state.planner = HighLevelPlanner()
    st.session_state.history = []
    st.session_state.controller.reset()
    st.session_state.controller.set_obstacles(get_environment("Empty Room"))

if reset_btn:
    st.session_state.controller.reset()
    st.session_state.controller.set_obstacles(get_environment(env_name))
    st.session_state.history = []
    st.rerun()

if run_btn and instruction.strip():
    # Update obstacles if environment changed
    st.session_state.controller.set_obstacles(get_environment(env_name))

    cmd = st.session_state.planner.parse(instruction)
    st.session_state.controller.execute(cmd)
    st.session_state.history.append({
        "instruction": instruction,
        "mid_level": str(cmd),
        "x": round(st.session_state.controller.state.x, 2),
        "y": round(st.session_state.controller.state.y, 2),
        "yaw": round(math.degrees(st.session_state.controller.state.yaw), 1)
    })

# Main area
col_left, col_right = st.columns([1.4, 1])

with col_left:
    fig = draw_world(st.session_state.controller, title=f"Environment: {env_name}")
    st.pyplot(fig)
    plt.close(fig)

with col_right:
    st.subheader("Current State")
    st.metric("X", f"{st.session_state.controller.state.x:.2f} m")
    st.metric("Y", f"{st.session_state.controller.state.y:.2f} m")
    st.metric("Yaw", f"{math.degrees(st.session_state.controller.state.yaw):.1f}°")

    st.subheader("Command History")
    if st.session_state.history:
        for i, h in enumerate(reversed(st.session_state.history[-6:]), 1):
            st.markdown(f"**{i}.** `{h['instruction']}` → `{h['mid_level']}`")
            st.caption(f"Position: ({h['x']}, {h['y']}) | Yaw: {h['yaw']}°")
    else:
        st.info("No commands executed yet.")

st.markdown("---")
st.markdown("**NaVILA-Lite** · Hierarchical design inspired by [NaVILA (RSS 2025)](https://navila-bot.github.io/)")
