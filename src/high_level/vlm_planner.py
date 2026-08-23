"""
Map-Context Hybrid Planner with optional lightweight VLM.

Primary path: robust heuristic (always works)
Optional path: Hugging Face Inference API (Phi-3 / similar) with map context
"""

from typing import List, Optional
from dataclasses import dataclass
import re
import json
import os

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
    def __init__(self, use_vlm: bool = False, hf_token: Optional[str] = None):
        self.use_vlm = use_vlm
        self.hf_token = hf_token or os.environ.get("HF_TOKEN", None)

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

    def _heuristic_parse(self, instruction: str) -> List[MidLevelCommand]:
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

    def _try_vlm(self, instruction: str, map_context: str) -> Optional[List[MidLevelCommand]]:
        """Optional lightweight VLM call via HF Inference API."""
        if not self.use_vlm or not self.hf_token:
            return None
        try:
            import requests
            prompt = (
                "You are a robot navigation planner. "
                "Given the map context and the human instruction, "
                "output ONLY a JSON list of commands. "
                "Allowed actions: move_forward (meters), turn_left (degrees), "
                "turn_right (degrees), stop, return_home.\n\n"
                f"Map context: {map_context}\n"
                f"Instruction: {instruction}\n\n"
                "JSON:"
            )
            API_URL = "https://api-inference.huggingface.co/models/microsoft/Phi-3-mini-4k-instruct"
            headers = {"Authorization": f"Bearer {self.hf_token}"}
            payload = {"inputs": prompt, "parameters": {"max_new_tokens": 120, "return_full_text": False}}
            r = requests.post(API_URL, headers=headers, json=payload, timeout=15)
            if r.status_code != 200:
                return None
            text = r.json()[0]["generated_text"] if isinstance(r.json(), list) else str(r.json())
            # Extract JSON array
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if not match:
                return None
            data = json.loads(match.group(0))
            commands = []
            for item in data:
                action = item.get("action", "").lower()
                value = item.get("value", None)
                if action in ["move_forward", "turn_left", "turn_right", "stop", "return_home"]:
                    commands.append(MidLevelCommand(action, value, source="vlm"))
            return commands if commands else None
        except Exception:
            return None

    def parse(self, instruction: str, map_context: Optional[str] = None) -> List[MidLevelCommand]:
        map_context = map_context or "No detailed map context available."
        # Try VLM first if enabled
        if self.use_vlm:
            vlm_result = self._try_vlm(instruction, map_context)
            if vlm_result:
                return vlm_result
        # Always fall back to heuristic
        return self._heuristic_parse(instruction)

    def build_map_context_summary(self, num_buildings: int, num_roads: int,
                                  lat: float, lon: float) -> str:
        return (
            f"Robot at ({lat:.5f}, {lon:.5f}). "
            f"Nearby: {num_buildings} buildings (obstacles), {num_roads} road segments. "
            f"Prefer roads, avoid buildings."
        )
