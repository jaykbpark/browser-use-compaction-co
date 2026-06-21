from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from browserdelta.config import get_settings
from browserdelta.main import app
from browserdelta.schemas import (
    ActionResult,
    BrowserAction,
    CompactObservation,
    InteractiveElement,
    PageState,
    RunManifest,
    StatePointer,
    StepRecord,
)
from browserdelta.storage import write_compact_observations, write_json, write_manifest, write_steps


def test_api_reads_manifest_steps_path_and_serves_run_files(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNS_DIR", str(tmp_path))
    get_settings.cache_clear()

    run_path = tmp_path / "api_contract"
    (run_path / "steps").mkdir(parents=True)
    (run_path / "steps" / "step_001_after.png").write_bytes(b"fake png")
    write_manifest(
        run_path,
        RunManifest(
            run_id="api_contract",
            start_url="https://example.com",
            mode="local",
            steps_path="records/custom_steps.jsonl",
        ),
    )
    write_steps(
        run_path,
        [
            StepRecord(
                step=1,
                action=BrowserAction(type="click", target="Example"),
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
        ],
    )

    client = TestClient(app)

    run_response = client.get("/api/runs/api_contract")
    assert run_response.status_code == 200
    assert run_response.json()["steps"][0]["step"] == 1

    file_response = client.get("/api/runs/api_contract/files/steps/step_001_after.png")
    assert file_response.status_code == 200
    assert file_response.content == b"fake png"

    (tmp_path / "outside.txt").write_text("outside")
    traversal_response = client.get("/api/runs/api_contract/files/%2E%2E/outside.txt")
    assert traversal_response.status_code == 400

    get_settings.cache_clear()


def test_api_evaluates_run_and_returns_eval_report(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNS_DIR", str(tmp_path))
    get_settings.cache_clear()

    run_path = tmp_path / "api_eval"
    write_manifest(
        run_path,
        RunManifest(
            run_id="api_eval",
            start_url="https://example.com",
            mode="local",
            metadata={"goal": "Refresh the chart and continue."},
        ),
    )
    write_steps(
        run_path,
        [
            _step(1, BrowserAction(type="click", target="Refresh chart")),
            _step(2, BrowserAction(type="click", target="Continue")),
        ],
    )
    write_compact_observations(
        run_path,
        [
            CompactObservation(
                step=1,
                action_result="success",
                summary="Visual state changed by 3.3%.",
                llm_observation="Visual state changed by 3.3%. Current interactive elements: e1 button: Continue",
                interactive=[InteractiveElement(ref="e1", role="button", name="Continue")],
                fallback="crop",
                route="crop_with_context",
                tokens_estimate=20,
                baseline_tokens_estimate=500,
                reduction_pct=80,
            )
        ],
    )
    _write_after_state(
        run_path,
        1,
        text=["Chart updated"],
        interactive=[InteractiveElement(ref="e1", role="button", name="Continue")],
    )
    _write_after_state(
        run_path,
        2,
        text=["Checkout ready"],
        interactive=[InteractiveElement(ref="e1", role="button", name="Continue")],
    )

    client = TestClient(app)

    eval_response = client.post("/api/runs/api_eval/eval")
    assert eval_response.status_code == 200
    assert eval_response.json()["report"]["passed_steps"] == 1

    run_response = client.get("/api/runs/api_eval")
    assert run_response.status_code == 200
    assert run_response.json()["eval_report"]["next_action_accuracy"] == 1.0

    full_state_response = client.post("/api/runs/api_eval/eval?context_mode=full_state")
    assert full_state_response.status_code == 200
    assert full_state_response.json()["report"]["context_mode"] == "full_state"

    compare_response = client.post("/api/runs/api_eval/eval/compare?predictor=heuristic")
    assert compare_response.status_code == 200
    assert compare_response.json()["comparison"]["summary"]["compact_passed_steps"] == 1
    assert (
        compare_response.json()["comparison"]["summary"]["baseline_context_mode"]
        == "vision_full_state"
    )

    run_response = client.get("/api/runs/api_eval")
    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["eval_full_state_report"]["context_mode"] == "full_state"
    assert payload["eval_vision_full_state_report"]["context_mode"] == "vision_full_state"
    assert payload["eval_comparison"]["summary"]["token_reduction_pct"] > 0

    get_settings.cache_clear()


def _step(step: int, action: BrowserAction) -> StepRecord:
    return StepRecord(
        step=step,
        action=action,
        result=ActionResult(ok=True),
        before=StatePointer(
            screenshot=f"steps/step_{step:03d}_before.png",
            state=f"steps/step_{step:03d}_before.json",
        ),
        after=StatePointer(
            screenshot=f"steps/step_{step:03d}_after.png",
            state=f"steps/step_{step:03d}_after.json",
        ),
    )


def _write_after_state(
    run_path: Path,
    step: int,
    text: list[str],
    interactive: list[InteractiveElement],
) -> None:
    write_json(
        run_path / f"steps/step_{step:03d}_after.json",
        PageState(
            url="https://example.com",
            title="Example",
            text=text,
            interactive=interactive,
            screenshot=f"steps/step_{step:03d}_after.png",
        ),
    )
