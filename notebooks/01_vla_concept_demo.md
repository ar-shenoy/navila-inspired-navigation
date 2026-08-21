# 01 – VLA Concept Demo (High-Level Planner)

This notebook demonstrates the **high-level** part of a NaVILA-style architecture.

> Language Instruction → Mid-level Spatial Command

In the full NaVILA system this is done by a large Vision-Language Model.  
Here we use a clean, interpretable planner so the idea is easy to understand and runs on any hardware (including Kaggle T4).

---

## 1. Install & Import

```python
# If running on Kaggle or Colab you can skip local install
!pip install -q numpy

from dataclasses import dataclass
from typing import Optional
import re
```

---

## 2. Mid-Level Command Definition

```python
@dataclass
class MidLevelCommand:
    action: str                    # "move_forward", "turn_left", "turn_right", "stop"
    value: Optional[float] = None  # meters or degrees
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
```

---

## 3. Simple Language Planner (High-Level)

```python
class SimpleLanguagePlanner:
    def __init__(self):
        self.forward_words = ["forward", "ahead", "straight", "go", "move", "walk"]
        self.left_words = ["left"]
        self.right_words = ["right"]
        self.stop_words = ["stop", "halt", "wait"]

    def parse(self, instruction: str, image_description: Optional[str] = None) -> MidLevelCommand:
        instruction = instruction.lower().strip()

        if any(w in instruction for w in self.stop_words):
            return MidLevelCommand(action="stop", raw_text=instruction)

        numbers = re.findall(r"(\d+\.?\d*)", instruction)
        value = float(numbers[0]) if numbers else None

        if any(w in instruction for w in self.left_words):
            angle = value if value is not None else 30.0
            return MidLevelCommand(action="turn_left", value=angle, raw_text=instruction)

        if any(w in instruction for w in self.right_words):
            angle = value if value is not None else 30.0
            return MidLevelCommand(action="turn_right", value=angle, raw_text=instruction)

        if any(w in instruction for w in self.forward_words) or value is not None:
            distance = value if value is not None else 0.75
            if distance > 10:          # treat large numbers as cm
                distance = distance / 100.0
            return MidLevelCommand(action="move_forward", value=distance, raw_text=instruction)

        return MidLevelCommand(action="move_forward", value=0.5, raw_text=instruction)
```

---

## 4. Demo

```python
planner = SimpleLanguagePlanner()

test_cases = [
    "Move forward 75cm",
    "Turn left 30 degrees",
    "Go straight ahead",
    "Turn right",
    "Stop near the door",
    "Walk forward 1.5 meters",
    "Move forward and stop at the red chair",
]

print("=== High-Level Planner Demo (NaVILA-style mid-level commands) ===\n")

for instr in test_cases:
    cmd = planner.parse(instr)
    print(f"Instruction : {instr}")
    print(f"Mid-level   : {cmd}")
    print(f"Structured  : {{'action': '{cmd.action}', 'value': {cmd.value}}}")
    print("-" * 60)
```

---

## 5. How this maps to NaVILA

| NaVILA Component       | In this demo                          |
|------------------------|---------------------------------------|
| Vision-Language Model  | SimpleLanguagePlanner (rule-based)    |
| Mid-level command      | `MidLevelCommand` object              |
| Low-level policy       | (next notebook)                       |

In a full system the `SimpleLanguagePlanner` would be replaced by a large VLM that also looks at the camera image.

---

## Next

- `02_simple_navigation_sim.ipynb` → connect the mid-level command to a basic controller
- Later: replace the rule-based planner with a real (small) Vision-Language model that can run on T4
