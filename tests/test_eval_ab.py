from pathlib import Path

from PIL import Image

from browserdelta.eval.ab import (
    EvalConfig,
    _needs_grounding,
    estimate_image_tokens,
    estimate_text_tokens,
    evaluate_run,
)
from browserdelta.schemas import (
    ActionResult,
    BrowserAction,
    InteractiveElement,
    PageState,
    StatePointer,
    StepRecord,
)
from browserdelta.storage import append_jsonl, write_json, write_manifest
from browserdelta.schemas import RunManifest


def test_estimate_text_tokens_matches_codec_heuristic():
    assert estimate_text_tokens("") == 0
    assert estimate_text_tokens("abcd") == 1
    assert estimate_text_tokens("a" * 400) == 100


def test_needs_grounding_excludes_selectors_and_targetless_actions():
    assert _needs_grounding(BrowserAction(type="click", target="Login")) is True
    assert _needs_grounding(BrowserAction(type="click", target="css=.cart")) is False
    assert _needs_grounding(BrowserAction(type="press", key="Enter")) is False


def test_estimate_image_tokens_high_detail_tiling():
    # 1280x800 scales to 1228x768 -> 3x2 tiles -> 85 + 170*6.
    assert estimate_image_tokens(1280, 800) == 1105
    assert estimate_image_tokens(0, 0) == 0


def _write_png(path: Path, color: str = "white") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (10, 10), color).save(path)


def _write_step(
    run_path: Path,
    step: int,
    action: BrowserAction,
    before: PageState,
    after: PageState,
) -> None:
    steps_dir = run_path / "steps"
    before_shot = steps_dir / f"step_{step:03d}_before.png"
    after_shot = steps_dir / f"step_{step:03d}_after.png"
    before_state = steps_dir / f"step_{step:03d}_before.json"
    after_state = steps_dir / f"step_{step:03d}_after.json"

    _write_png(before_shot)
    _write_png(after_shot)
    write_json(before_state, before)
    write_json(after_state, after)

    record = StepRecord(
        step=step,
        action=action,
        result=ActionResult(ok=True, message="ok"),
        before=StatePointer(screenshot=f"steps/step_{step:03d}_before.png", state=f"steps/step_{step:03d}_before.json"),
        after=StatePointer(screenshot=f"steps/step_{step:03d}_after.png", state=f"steps/step_{step:03d}_after.json"),
    )
    append_jsonl(run_path / "steps.jsonl", record)


def _state(url: str, elements: list[InteractiveElement]) -> PageState:
    return PageState(url=url, title="t", text=[], interactive=elements)


def test_compact_drops_truncated_element_baseline_does_not(tmp_path: Path):
    """Element needed for the next action is beyond the compact text limit."""

    run_path = tmp_path / "trunc"
    write_manifest(run_path, RunManifest(run_id="trunc", start_url="https://x", mode="local"))

    fillers = [InteractiveElement(ref=f"e{i}", role="button", name=f"Filler {i}") for i in range(1, 14)]
    target = InteractiveElement(ref="e14", role="button", name="Target")
    after = _state("https://x", fillers + [target])
    before = _state("https://x", [])

    _write_step(run_path, 1, BrowserAction(type="click", target="Start"), before, after)
    _write_step(run_path, 2, BrowserAction(type="click", target="Target"), after, after)

    task = {
        "id": "trunc",
        "goal": "g",
        "actions": [
            {"type": "click", "target": "Start"},
            {"type": "click", "target": "Target"},
        ],
    }

    report = evaluate_run(run_path, task=task, config=EvalConfig())
    sample = report["steps"][0]["next_action_eval"]

    assert sample["needs_grounding"] is True
    assert sample["baseline"]["match"] is True  # full state keeps "Target"
    assert sample["compact"]["match"] is False  # truncated out of first 12
    assert sample["compact"]["predicted"]["type"] == "request_full_screenshot"

    summary = report["summary"]["next_action"]
    assert summary["baseline_accuracy"] == 1.0
    assert summary["compact_accuracy"] == 0.0


def test_compact_saves_tokens_and_preserves_grounding(tmp_path: Path):
    run_path = tmp_path / "ok"
    write_manifest(run_path, RunManifest(run_id="ok", start_url="https://x", mode="local"))

    login = [
        InteractiveElement(ref="e1", role="textbox", name="Username"),
        InteractiveElement(ref="e2", role="textbox", name="Password"),
        InteractiveElement(ref="e3", role="button", name="Login"),
    ]
    state = _state("https://x", login)
    _write_step(run_path, 1, BrowserAction(type="type", target="Username", text="u"), state, state)
    _write_step(run_path, 2, BrowserAction(type="type", target="Password", text="p"), state, state)

    task = {
        "id": "ok",
        "goal": "g",
        "actions": [
            {"type": "type", "target": "Username", "text": "u"},
            {"type": "type", "target": "Password", "text": "p"},
        ],
    }

    report = evaluate_run(run_path, task=task)
    summary = report["summary"]

    assert summary["tokens"]["compact_total"] < summary["tokens"]["baseline_total"]
    assert summary["tokens"]["savings_pct"] > 0
    assert summary["next_action"]["compact_accuracy"] == 1.0
    assert summary["routes_compact"].get("structural") == 2
    assert summary["fallback"]["fallback_rate"] == 0.0
