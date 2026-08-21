"""
Low-Level Controller with explicit Reward System (RL-inspired)

This module implements a clear reward function and a reactive policy
that tries to maximize reward while executing mid-level commands.

Reward design (common in navigation RL):
- Positive reward for progress toward the commanded direction
- Strong negative reward for collisions / near-collisions
- Small time penalty
- Bonus for successful execution of the mid-level command
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
import math
import numpy as np


@dataclass
class RobotState:
    x: float = 1.0
    y: float = 1.0
    yaw: float = 0.0  # radians


@dataclass
class StepResult:
    state: RobotState
    reward: float
    collision: bool
    done: bool
    info: Dict = field(default_factory=dict)


class RewardCalculator:
    """
    Explicit reward function for navigation.
    """

    def __init__(
        self,
        progress_scale: float = 1.0,
        collision_penalty: float = -5.0,
        near_collision_penalty: float = -1.5,
        time_penalty: float = -0.01,
        success_bonus: float = 2.0,
        near_threshold: float = 0.55,
    ):
        self.progress_scale = progress_scale
        self.collision_penalty = collision_penalty
        self.near_collision_penalty = near_collision_penalty
        self.time_penalty = time_penalty
        self.success_bonus = success_bonus
        self.near_threshold = near_threshold

    def compute(
        self,
        prev_state: RobotState,
        new_state: RobotState,
        obstacles: List[Tuple[float, float, float]],
        commanded_distance: float = 0.0,
        collision: bool = False,
        command_finished: bool = False,
    ) -> float:
        reward = 0.0

        # 1. Progress reward (how much we moved in the facing direction)
        dx = new_state.x - prev_state.x
        dy = new_state.y - prev_state.y
        forward_progress = dx * math.cos(prev_state.yaw) + dy * math.sin(prev_state.yaw)
        reward += self.progress_scale * forward_progress

        # 2. Collision / near-collision
        if collision:
            reward += self.collision_penalty
        else:
            min_dist = float("inf")
            for ox, oy, r in obstacles:
                dist = math.hypot(new_state.x - ox, new_state.y - oy) - r
                min_dist = min(min_dist, dist)
            if min_dist < self.near_threshold:
                reward += self.near_collision_penalty * (self.near_threshold - min_dist)

        # 3. Time penalty
        reward += self.time_penalty

        # 4. Success bonus when the mid-level command is completed
        if command_finished:
            reward += self.success_bonus

        return reward


class RLInspiredController:
    """
    Low-level controller that uses an explicit reward function
    and a reactive policy to maximize it while following mid-level commands.
    """

    def __init__(self, world_size: float = 8.0):
        self.world_size = world_size
        self.state = RobotState()
        self.trajectory: List[Tuple[float, float]] = []
        self.obstacles: List[Tuple[float, float, float]] = []
        self.reward_fn = RewardCalculator()
        self.total_reward = 0.0
        self.episode_rewards: List[float] = []

    def reset(self, x: float = 1.0, y: float = 1.0, yaw: float = 0.0):
        self.state = RobotState(x=x, y=y, yaw=yaw)
        self.trajectory = [(x, y)]
        self.total_reward = 0.0
        self.episode_rewards = []

    def set_obstacles(self, obstacles: List[Tuple[float, float, float]]):
        self.obstacles = obstacles

    def _is_collision(self, x: float, y: float, robot_radius: float = 0.25) -> bool:
        for ox, oy, r in self.obstacles:
            if math.hypot(x - ox, y - oy) < (r + robot_radius):
                return True
        if x < 0.3 or y < 0.3 or x > self.world_size - 0.3 or y > self.world_size - 0.3:
            return True
        return False

    def _select_best_action(
        self, base_yaw: float, step_size: float, candidate_deltas: List[float]
    ) -> Tuple[float, float, float, float]:
        """
        Try several possible headings and choose the one with highest immediate reward.
        This is a simple one-step greedy policy (common in reactive RL navigation).
        """
        best_reward = -float("inf")
        best_yaw = base_yaw
        best_x, best_y = self.state.x, self.state.y
        best_collision = False

        for delta in candidate_deltas:
            test_yaw = base_yaw + delta
            nx = self.state.x + step_size * math.cos(test_yaw)
            ny = self.state.y + step_size * math.sin(test_yaw)
            collision = self._is_collision(nx, ny)

            # Temporary state for reward calculation
            new_state = RobotState(x=nx, y=ny, yaw=test_yaw)
            r = self.reward_fn.compute(
                prev_state=self.state,
                new_state=new_state,
                obstacles=self.obstacles,
                collision=collision,
                command_finished=False,
            )

            if r > best_reward:
                best_reward = r
                best_yaw = test_yaw
                best_x, best_y = nx, ny
                best_collision = collision

        return best_x, best_y, best_yaw, best_reward, best_collision

    def execute(self, action: str, value: Optional[float] = None, steps: int = 25) -> StepResult:
        """
        Execute a mid-level command using reward-driven reactive policy.
        """
        action = action.lower()
        prev_state = RobotState(x=self.state.x, y=self.state.y, yaw=self.state.yaw)
        step_rewards = []

        if action == "stop":
            r = self.reward_fn.compute(
                prev_state, self.state, self.obstacles, command_finished=True
            )
            self.total_reward += r
            self.episode_rewards.append(r)
            return StepResult(self.state, r, False, True, {"total_reward": self.total_reward})

        if action == "move_forward":
            distance = value if value is not None else 0.6
            step_size = distance / steps

            for i in range(steps):
                # Candidate turning angles (reactive action space)
                deltas = [0.0, 0.25, -0.25, 0.5, -0.5, 0.85, -0.85, 1.2, -1.2]

                nx, ny, new_yaw, r, collision = self._select_best_action(
                    self.state.yaw, step_size, deltas
                )

                self.state.x = nx
                self.state.y = ny
                self.state.yaw = (new_yaw + math.pi) % (2 * math.pi) - math.pi
                self.trajectory.append((self.state.x, self.state.y))

                step_rewards.append(r)
                self.total_reward += r

                if collision:
                    break

            command_finished = True
            final_r = sum(step_rewards)
            self.episode_rewards.append(final_r)

            return StepResult(
                state=self.state,
                reward=final_r,
                collision=collision if "collision" in locals() else False,
                done=True,
                info={
                    "total_reward": self.total_reward,
                    "step_rewards": step_rewards,
                    "distance_commanded": distance,
                },
            )

        elif action in ["turn_left", "turn_right"]:
            angle_deg = value if value is not None else 30.0
            angle_rad = math.radians(angle_deg)
            if action == "turn_right":
                angle_rad = -angle_rad

            self.state.yaw += angle_rad
            self.state.yaw = (self.state.yaw + math.pi) % (2 * math.pi) - math.pi
            self.trajectory.append((self.state.x, self.state.y))

            r = self.reward_fn.compute(
                prev_state, self.state, self.obstacles, command_finished=True
            )
            self.total_reward += r
            self.episode_rewards.append(r)

            return StepResult(
                state=self.state,
                reward=r,
                collision=False,
                done=True,
                info={"total_reward": self.total_reward},
            )

        return StepResult(self.state, 0.0, False, True, {})

    def get_trajectory(self):
        return np.array(self.trajectory)

    def get_total_reward(self):
        return self.total_reward
