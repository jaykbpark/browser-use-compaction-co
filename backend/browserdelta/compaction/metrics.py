from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image

from browserdelta.schemas import PageState


def estimate_text_tokens(text: str) -> int:
    return max(1, round(len(text) / 4))


def estimate_state_tokens(state: PageState) -> int:
    payload = json.dumps(state.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)
    return estimate_text_tokens(payload)


def estimate_image_tokens(image_path: Path) -> int:
    """Approximate image-token cost with a simple tile heuristic.

    This is intentionally model-agnostic enough for eval comparisons. The exact
    tokenization depends on the LLM provider, but bigger screenshots should cost
    more than small crops.
    """

    if not image_path.exists():
        return 0
    with Image.open(image_path) as image:
        width, height = image.size

    tiles = max(1, math.ceil(width / 512) * math.ceil(height / 512))
    return 85 + tiles * 170


def estimate_raw_baseline_tokens(after_state: PageState, screenshot_path: Path) -> int:
    return estimate_state_tokens(after_state) + estimate_image_tokens(screenshot_path)


def reduction_pct(baseline_tokens: int, compact_tokens: int) -> float:
    if baseline_tokens <= 0:
        return 0.0
    return round(max(0.0, (baseline_tokens - compact_tokens) / baseline_tokens * 100), 2)
