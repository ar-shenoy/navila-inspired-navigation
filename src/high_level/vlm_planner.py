"""
High-Level Planner with real lightweight Vision-Language Model (SmolVLM)
Falls back to improved heuristic if model cannot be loaded.
"""

from dataclasses import dataclass
from typing import Optional
import re
import torch

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

class VLMHighLevelPlanner:
    def __init__(self, model_name: str = "HuggingFaceTB/SmolVLM-500M-Instruct", device: str = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.processor = None
        self.model_name = model_name
        self._load_model()

        self.forward_words = ["forward", "ahead", "straight", "go", "move", "walk", "advance"]
        self.left_words = ["left"]
        self.right_words = ["right"]
        self.stop_words = ["stop", "halt", "wait", "stay"]

    def _load_model(self):
        try:
            from transformers import AutoProcessor, AutoModelForVision2Seq
            print(f"Loading VLM: {self.model_name} on {self.device} ...")
            self.processor = AutoProcessor.from_pretrained(self.model_name)
            self.model = AutoModelForVision2Seq.from_pretrained(
                self.model_name,
                torch_dtype=torch.bfloat16 if self.device == "cuda" else torch.float32,
                device_map="auto" if self.device == "cuda" else None,
            )
            if self.device == "cpu":
                self.model = self.model.to(self.device)
            self.model.eval()
            print("VLM loaded successfully.")
        except Exception as e:
            print(f"Could not load VLM ({e}). Falling back to heuristic.")
            self.model = None
            self.processor = None

    def _heuristic_parse(self, instruction: str) -> MidLevelCommand:
        text = instruction.lower().strip()
        if any(w in text for w in self.stop_words):
            return MidLevelCommand("stop", raw_text=instruction, confidence=0.95, source="heuristic")

        numbers = re.findall(r"(\d+\.?\d*)", text)
        value = float(numbers[0]) if numbers else None

        if any(w in text for w in self.left_words):
            angle = value if value is not None else 30.0
            return MidLevelCommand("turn_left", angle, instruction, 0.9, "heuristic")
        if any(w in text for w in self.right_words):
            angle = value if value is not None else 30.0
            return MidLevelCommand("turn_right", angle, instruction, 0.9, "heuristic")

        distance = value if value is not None else 0.7
        if distance > 5:
            distance /= 100.0
        return MidLevelCommand("move_forward", distance, instruction, 0.85, "heuristic")

    def _vlm_generate(self, instruction: str, image=None) -> Optional[MidLevelCommand]:
        if self.model is None or self.processor is None:
            return None
        try:
            prompt_text = (
                f"You are a robot navigation planner. "
                f"Given the instruction: '{instruction}'. "
                f"Reply with only one short command in this exact format:\n"
                f"move_forward <meters>  OR  turn_left <degrees>  OR  turn_right <degrees>  OR  stop\n"
                f"Example: move_forward 0.8"
            )
            messages = [{"role": "user", "content": [{"type": "text", "text": prompt_text}]}]
            if image is not None:
                messages[0]["content"].insert(0, {"type": "image"})

            prompt = self.processor.apply_chat_template(messages, add_generation_prompt=True)
            if image is not None:
                inputs = self.processor(text=prompt, images=[image], return_tensors="pt")
            else:
                inputs = self.processor(text=prompt, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                generated_ids = self.model.generate(**inputs, max_new_tokens=32, do_sample=False)

            text = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0].lower().strip()

            if "stop" in text:
                return MidLevelCommand("stop", raw_text=instruction, confidence=0.8, source="vlm")

            numbers = re.findall(r"(\d+\.?\d*)", text)
            value = float(numbers[0]) if numbers else None

            if "left" in text:
                angle = value if value is not None else 30.0
                return MidLevelCommand("turn_left", angle, instruction, 0.75, "vlm")
            if "right" in text:
                angle = value if value is not None else 30.0
                return MidLevelCommand("turn_right", angle, instruction, 0.75, "vlm")
            if "forward" in text or "move" in text:
                dist = value if value is not None else 0.7
                if dist > 5:
                    dist /= 100.0
                return MidLevelCommand("move_forward", dist, instruction, 0.75, "vlm")
            return None
        except Exception as e:
            print(f"VLM generation failed: {e}")
            return None

    def parse(self, instruction: str, image=None, use_vlm: bool = True) -> MidLevelCommand:
        if use_vlm:
            vlm_result = self._vlm_generate(instruction, image)
            if vlm_result is not None:
                return vlm_result
        return self._heuristic_parse(instruction)
