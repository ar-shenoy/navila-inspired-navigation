from dataclasses import dataclass
from typing import Optional
import re


@dataclass
class MidLevelCommand:
    action: str
    value: Optional[float] = None
    raw_text: str = ""
    confidence: float = 1.0
    source: str = "heuristic"

    def __str__(self):
        if self.action == "stop":
            return "stop"
        if self.value is not None:
            if "turn" in self.action:
                return f"{self.action.replace('_', ' ')} {self.value:.0f}°"
            return f"{self.action.replace('_', ' ')} {self.value:.2f}m"
        return self.action.replace("_", " ")


class AIHighLevelPlanner:
    def __init__(self):
        self.forward_words = ["forward", "ahead", "straight", "go", "move", "walk", "advance", "proceed"]
        self.left_words = ["left"]
        self.right_words = ["right"]
        self.stop_words = ["stop", "halt", "wait", "stay"]
        self.back_words = ["back", "backward", "reverse"]

    def _extract_number(self, text: str) -> Optional[float]:
        numbers = re.findall(r"(\d+\.?\d*)", text)
        return float(numbers[0]) if numbers else None

    def _heuristic_parse(self, instruction: str) -> MidLevelCommand:
        text = instruction.lower().strip()

        if any(w in text for w in self.stop_words):
            return MidLevelCommand("stop", raw_text=instruction, confidence=0.95)

        value = self._extract_number(text)

        if any(w in text for w in self.left_words):
            angle = value if value is not None else 30.0
            if "slight" in text or "little" in text:
                angle = min(angle, 20.0)
            if "sharp" in text or "hard" in text:
                angle = max(angle, 60.0)
            return MidLevelCommand("turn_left", angle, instruction, confidence=0.9)

        if any(w in text for w in self.right_words):
            angle = value if value is not None else 30.0
            if "slight" in text or "little" in text:
                angle = min(angle, 20.0)
            if "sharp" in text or "hard" in text:
                angle = max(angle, 60.0)
            return MidLevelCommand("turn_right", angle, instruction, confidence=0.9)

        if any(w in text for w in self.back_words):
            distance = value if value is not None else 0.4
            if distance > 5:
                distance /= 100.0
            return MidLevelCommand("move_forward", -abs(distance), instruction, confidence=0.8)

        distance = value if value is not None else 0.7
        if distance > 5:
            distance /= 100.0
        if "slowly" in text or "careful" in text:
            distance *= 0.6
        if "quickly" in text or "fast" in text:
            distance *= 1.3

        return MidLevelCommand("move_forward", distance, instruction, confidence=0.85)

    def _ai_generate(self, instruction: str, image_description: Optional[str] = None) -> Optional[MidLevelCommand]:
        # Placeholder for real small VLM / LLM integration
        return None

    def parse(self, instruction: str, image_description: Optional[str] = None, use_ai: bool = True) -> MidLevelCommand:
        if use_ai:
            ai_result = self._ai_generate(instruction, image_description)
            if ai_result is not None:
                ai_result.source = "ai"
                return ai_result
        result = self._heuristic_parse(instruction)
        result.source = "heuristic"
        return result
