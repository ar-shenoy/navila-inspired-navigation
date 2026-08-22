"""
Improved Visualization for NaVILA-Lite
Cleaner 2.5D-style top-down rendering.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, FancyBboxPatch, Polygon
from matplotlib.collections import LineCollection
import math
from typing import List, Tuple, Optional


def create_robot_patch(x, y, yaw, size=0.28):
    """Create a simple robot shape (circle + direction triangle)."""
    # Body
    body = Circle((x, y), size, facecolor="#2ecc71", edgecolor="#1e8449", linewidth=1.5, zorder=5)

    # Direction indicator (triangle)
    tip_x = x + size * 1.35 * math.cos(yaw)
    tip_y = y + size * 1.35 * math.sin(yaw)
    left_x = x + size * 0.6 * math.cos(yaw + 2.3)
    left_y = y + size * 0.6 * math.sin(yaw + 2.3)
    right_x = x + size * 0.6 * math.cos(yaw - 2.3)
    right_y = y + size * 0.6 * math.sin(yaw - 2.3)

    triangle = Polygon(
        [[tip_x, tip_y], [left_x, left_y], [right_x, right_y]],
        facecolor="#27ae60", edgecolor="#1e8449", linewidth=1.0, zorder=6
    )
    return body, triangle


def render_world(
    trajectory: List[Tuple[float, float]],
    robot_state,
    obstacles: List[Tuple[float, float, float]],
    world_size: float = 8.0,
    total_reward: float = 0.0,
    title: str = "NaVILA-Lite",
    show_grid: bool = True,
):
    """
    Render a cleaner top-down view.
    """
    fig, ax = plt.subplots(figsize=(9, 9), facecolor="#f8f9fa")
    ax.set_facecolor("#f0f2f5")

    ax.set_xlim(-0.2, world_size + 0.2)
    ax.set_ylim(-0.2, world_size + 0.2)
    ax.set_aspect("equal")

    # Soft grid
    if show_grid:
        ax.set_xticks(np.arange(0, world_size + 1, 1))
        ax.set_yticks(np.arange(0, world_size + 1, 1))
        ax.grid(True, color="#d0d5dd", linestyle="--", linewidth=0.7, alpha=0.7)

    # Border
    border = Rectangle((0, 0), world_size, world_size,
                       linewidth=2.5, edgecolor="#34495e", facecolor="none", zorder=1)
    ax.add_patch(border)

    # Obstacles with slight 3D feel (darker edge)
    for ox, oy, r in obstacles:
        # Shadow
        shadow = Circle((ox + 0.06, oy - 0.06), r, color="#000000", alpha=0.12, zorder=2)
        ax.add_patch(shadow)
        # Main body
        circle = Circle((ox, oy), r, facecolor="#e74c3c", edgecolor="#c0392b",
                        linewidth=1.8, alpha=0.9, zorder=3)
        ax.add_patch(circle)

    # Trajectory with gradient feel
    if len(trajectory) > 1:
        traj = np.array(trajectory)
        ax.plot(traj[:, 0], traj[:, 1], color="#3498db", linewidth=3.5, alpha=0.9,
                solid_capstyle="round", label="Path", zorder=4)
        # Start marker
        ax.scatter(traj[0, 0], traj[0, 1], s=80, c="#2ecc71", edgecolors="#1e8449",
                   zorder=7, label="Start")

    # Robot
    body, triangle = create_robot_patch(robot_state.x, robot_state.y, robot_state.yaw)
    ax.add_patch(body)
    ax.add_patch(triangle)

    # Info box
    info_text = (
        f"Position: ({robot_state.x:.2f}, {robot_state.y:.2f})\n"
        f"Yaw: {math.degrees(robot_state.yaw):.1f}°\n"
        f"Total Reward: {total_reward:.2f}"
    )
    props = dict(boxstyle="round,pad=0.5", facecolor="white", edgecolor="#bdc3c7", alpha=0.92)
    ax.text(0.03, 0.97, info_text, transform=ax.transAxes, fontsize=10,
            verticalalignment="top", bbox=props, family="monospace", zorder=10)

    ax.set_xlabel("X (meters)", fontsize=11)
    ax.set_ylabel("Y (meters)", fontsize=11)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.legend(loc="lower right", framealpha=0.9)

    plt.tight_layout()
    return fig
