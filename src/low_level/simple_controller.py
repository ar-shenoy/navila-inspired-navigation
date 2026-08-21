"""
Simple Low-Level Controller
Takes mid-level commands from the high-level planner and simulates robot movement.

In a full NaVILA system this would be a visual locomotion RL policy.
Here we use a clean kinematic simulation so the hierarchical idea remains clear.
"""

from dataclasses import dataclass
from typing import List, Tuple
import math
import numpy as np


@dataclass
class RobotState:
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0  # radians

    def as_tuple(self):
        return (self.x, self.y, self.yaw)


class SimpleController:
    """
    Very simple differential-drive style controller.
    """

    def __init__(self, max_linear_speed=0.5, max_angular_speed=1.0):
        self.max_linear_speed = max_linear_speed      # m/s
        self.max_angular_speed = max_angular_speed    # rad/s
        self.state = RobotState()
        self.trajectory: List[Tuple[float, float]] = [(0.0, 0.0)]

    def reset(self, x=0.0, y=0.0, yaw=0.0):
        self.state = RobotState(x=x, y=y, yaw=yaw)
        self.trajectory = [(x, y)]

    def execute(self, action: str, value: float = None, dt: float = 0.1):
        """
        Execute one mid-level command.
        Returns the final state after execution.
        """
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
                # keep yaw in [-pi, pi]
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
