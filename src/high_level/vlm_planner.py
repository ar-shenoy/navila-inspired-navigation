"""
Map-Context Hybrid Planner

High-level planner that can use:
1. Lightweight LLM via Hugging Face Inference API (optional)
2. Strong heuristic fallback (always available)

Map context (nearby roads / buildings summary) can be injected
to make the planner more environment-aware.
"""

from typing import List, Optional, Dict
from dataclasses import dataclass
import re
import json

@dataclass
class MidLevelCommand:
    action: str
    value: Optional[float] = None
    source: str = "heuristic"

    def __str__(self):
        if self.action == "stop":
            return "stop"
        if self.action == "return_home":
            return "return to start"
        if self.value is not None:
            if "turn" in self.action:
                return f"{self.action.replace('_', ' ')} {self.value:.0f}°"
            return f"{self.action.replace('_', ' ')} {self.value:.1f}m"
        return self.action.replace("_", " ")


class MapContextPlanner:
    """
    Hybrid high-level planner.
    - Tries structured parsing first (fast & reliable)
    - Has a slot for future / optional LLM call with map context
    """

    def __init__(self):
        self.forward_words = ["forward", "ahead", "straight", "go", "move", "walk", "advance"]
        self.left_words = ["left"]
        self.right_words = ["right"]
        self.stop_words = ["stop", "halt", "wait", "stay"]
        self.return_words = ["return", "back", "home", "original", "start"]

    def _heuristic_parse_single(self, text: str) -> MidLevelCommand:
        text = text.lower().strip()

        if any(w in text for w in self.return_words):
            return MidLevelCommand("return_home", source="heuristic")

        if any(w in text for w in self.stop_words):
            return MidLevelCommand("stop", source="heuristic")

        numbers = re.findall(r"(\d+\.?\d*)", text)
        value = float(numbers[0]) if numbers else None

        if any(w in text for w in self.left_words):
            return MidLevelCommand("turn_left", value if value is not None else 90.0, "heuristic")

        if any(w in text for w in self.right_words):
            return MidLevelCommand("turn_right", value if value is not None else 90.0, "heuristic")

        distance = value if value is not None else 30.0
        if "km" in text:
            distance = (value if value is not None else 1.0) * 1000.0

        return MidLevelCommand("move_forward", distance, "heuristic")

    def parse(self, instruction: str, map_context: Optional[str] = None) -> List[MidLevelCommand]:
        """
        Main entry point.
        map_context can later be used for LLM prompting.
        Currently uses robust multi-command heuristic.
        """
        # Split multi-commands
        parts = re.split(r",| and | then |\.", instruction.lower())
        parts = [p.strip() for p in parts if p.strip()]

        commands = []
        for part in parts:
            if any(w in part for w in self.forward_words + self.left_words + self.right_words +
                                     self.stop_words + self.return_words):
                commands.append(self._heuristic_parse_single(part))

        if not commands:
            commands.append(self._heuristic_parse_single(instruction))

        return commands

    def build_map_context_summary(self, num_buildings: int, num_roads: int,
                                  lat: float, lon: float) -> str:
        """Create a short text summary that can be fed to an LLM."""
        return (
            f"Robot is at approximately ({lat:.5f}, {lon:.5f}). "
            f"Nearby map data: {num_buildings} buildings (obstacles), "
            f"{num_roads} road segments. Prefer moving along roads and avoid buildings."
        )
