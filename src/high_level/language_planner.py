"""
Simplified High-Level Language Planner
Inspired by NaVILA's mid-level command generation.

This module takes a natural language instruction (and optionally an image description)
and outputs a structured mid-level navigation command.
"""

from dataclasses import dataclass
from typing import Optional
import re


@dataclass
class MidLevelCommand:
    action: str          # e.g. "move_forward", "turn_left", "turn_right", "stop"
    value: Optional[float] = None   # distance (meters) or angle (degrees)
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
    """
    A lightweight rule-based + keyword planner.
    In a full NaVILA system this would be replaced by a large Vision-Language Model.
    """

    def __init__(self):
        # Simple keyword patterns
        self.forward_words = ["forward", "ahead", "straight", "go", "move", "walk"]
        self.left_words = ["left"]
        self.right_words = ["right"]
        self.stop_words = ["stop", "halt", "wait"]

    def parse(self, instruction: str, image_description: Optional[str] = None) -> MidLevelCommand:
        instruction = instruction.lower().strip()

        # Stop command
        if any(w in instruction for w in self.stop_words):
            return MidLevelCommand(action="stop", raw_text=instruction)

        # Extract numbers (distance or angle)
        numbers = re.findall(r"(\d+\.?\d*)", instruction)
        value = float(numbers[0]) if numbers else None

        # Turn left
        if any(w in instruction for w in self.left_words):
            angle = value if value is not None else 30.0
            return MidLevelCommand(action="turn_left", value=angle, raw_text=instruction)

        # Turn right
        if any(w in instruction for w in self.right_words):
            angle = value if value is not None else 30.0
            return MidLevelCommand(action="turn_right", value=angle, raw_text=instruction)

        # Move forward (default)
        if any(w in instruction for w in self.forward_words) or value is not None:
            distance = value if value is not None else 0.75
            # Convert cm to meters if the number looks like cm
            if distance > 10:
                distance = distance / 100.0
            return MidLevelCommand(action="move_forward", value=distance, raw_text=instruction)

        # Fallback
        return MidLevelCommand(action="move_forward", value=0.5, raw_text=instruction)


if __name__ == "__main__":
    planner = SimpleLanguagePlanner()

    test_instructions = [
        "Move forward 75cm",
        "Turn left 30 degrees",
        "Go straight ahead",
        "Turn right",
        "Stop near the door",
        "Walk forward 1.5 meters",
    ]

    print("=== Simple Language Planner Demo ===\n")
    for instr in test_instructions:
        cmd = planner.parse(instr)
        print(f"Instruction : {instr}")
        print(f"Mid-level   : {cmd}")
        print(f"Structured  : action={cmd.action}, value={cmd.value}\n")
