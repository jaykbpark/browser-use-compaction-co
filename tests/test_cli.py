from __future__ import annotations

import json
from pathlib import Path

from browserdelta.cli import build_observation_payload, format_agent_observation, main
from browserdelta.schemas import (
    ActionResult,
    BrowserAction,
    CompactObservation,
    RunManifest,
    StatePointer,
    StepRecord,
)
from browserdelta.storage import append_jsonl, write_json


def test_observe_payload_is_agent_ready(tmp_path: Path):
    run_path = _write_compacted_run(tmp_path)

    payload = build_observation_payload(run_path, step=1)

    assert payload["run_id"] == "agent_demo"
    assert payload["step"] == 1
    assert payload["route"] == "crop_with_context"
    assert payload["artifacts"]["after_screenshot"] == "steps/step_001_after.png"
    assert payload["artifacts"]["crop_paths"] == ["crops/step_001/crop_01.png"]
    assert "Button appeared" in format_agent_observation(payload)


def test_observe_command_prints_json(tmp_path: Path, capsys):
    run_path = _write_compacted_run(tmp_path)

    assert main(["observe", str(run_path), "--step", "1", "--format", "json"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["summary"] == "Button appeared"
    assert output["tokens_estimate"] == 120
    assert output["baseline_tokens_estimate"] == 1200


def _write_compacted_run(tmp_path: Path) -> Path:
    run_path = tmp_path / "agent_demo"
    write_json(
        run_path / "run.json",
        RunManifest(
            run_id="agent_demo",
            start_url="https://example.com",
            mode="local",
        ),
    )
    append_jsonl(
        run_path / "steps.jsonl",
        StepRecord(
            step=1,
            action=BrowserAction(type="click", target="Open"),
            result=ActionResult(ok=True),
            before=StatePointer(
                screenshot="steps/step_001_before.png",
                state="steps/step_001_before.json",
            ),
            after=StatePointer(
                screenshot="steps/step_001_after.png",
                state="steps/step_001_after.json",
            ),
        ),
    )
    append_jsonl(
        run_path / "compact_observations.jsonl",
        CompactObservation(
            step=1,
            action_result="ok",
            summary="Button appeared",
            route="crop_with_context",
            fallback="crop",
            llm_observation="Button appeared. Click it next.",
            crop_paths=["crops/step_001/crop_01.png"],
            tokens_estimate=120,
            baseline_tokens_estimate=1200,
            reduction_pct=90.0,
        ),
    )
    return run_path
