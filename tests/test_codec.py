from pathlib import Path

from PIL import Image

from browserdelta.compaction.codec import compact_step
from browserdelta.schemas import (
    ActionResult,
    BrowserAction,
    InteractiveElement,
    PageState,
    StatePointer,
    StepRecord,
)
from browserdelta.storage import write_json


def test_compact_step_prefers_specific_validation_error(tmp_path: Path):
    steps = tmp_path / "steps"
    steps.mkdir()
    before_png = steps / "step_001_before.png"
    after_png = steps / "step_001_after.png"
    Image.new("RGB", (100, 100), "white").save(before_png)
    Image.new("RGB", (100, 100), "white").save(after_png)

    write_json(
        steps / "step_001_before.json",
        PageState(
            url="https://app.test/login",
            title="Login",
            text=["Login"],
            interactive=[
                InteractiveElement(ref="e1", role="textbox", name="Email"),
                InteractiveElement(ref="e2", role="button", name="Submit"),
            ],
        ),
    )
    write_json(
        steps / "step_001_after.json",
        PageState(
            url="https://app.test/login",
            title="Login",
            text=["Login", "Email is required"],
            interactive=[
                InteractiveElement(ref="e5", role="textbox", name="Email"),
                InteractiveElement(ref="e6", role="button", name="Submit"),
            ],
        ),
    )

    step = StepRecord(
        step=1,
        action=BrowserAction(type="click", target="Submit"),
        result=ActionResult(ok=True),
        before=StatePointer(
            screenshot="steps/step_001_before.png",
            state="steps/step_001_before.json",
        ),
        after=StatePointer(
            screenshot="steps/step_001_after.png",
            state="steps/step_001_after.json",
        ),
    )

    observation = compact_step(tmp_path, step)

    assert "Email is required" in observation.summary
    assert "Email is required" in observation.llm_observation
    assert observation.fallback == "none"
    assert observation.route == "text_only"
    assert observation.confidence > 0.85
    assert observation.tokens_estimate > 0
    assert observation.baseline_tokens_estimate > observation.tokens_estimate
    assert observation.reduction_pct > 0
