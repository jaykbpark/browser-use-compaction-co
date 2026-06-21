from pathlib import Path

from PIL import Image

from browserdelta.compaction.metrics import (
    estimate_image_tokens,
    estimate_raw_baseline_tokens,
    estimate_text_tokens,
    reduction_pct,
)
from browserdelta.schemas import PageState


def test_token_estimates_and_reduction(tmp_path: Path):
    screenshot = tmp_path / "screen.png"
    Image.new("RGB", (640, 480), "white").save(screenshot)
    state = PageState(url="https://example.com", title="Example", text=["hello world"])

    text_tokens = estimate_text_tokens("short observation")
    image_tokens = estimate_image_tokens(screenshot)
    baseline = estimate_raw_baseline_tokens(state, screenshot)

    assert text_tokens > 0
    assert image_tokens > 0
    assert baseline > image_tokens
    assert reduction_pct(baseline, text_tokens) > 50
