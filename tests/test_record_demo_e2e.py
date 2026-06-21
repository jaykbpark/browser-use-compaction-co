from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from browserdelta.schemas import CompactObservation, PageState, StepRecord
from browserdelta.storage import read_jsonl


def test_record_demo_local_checkout_records_and_compacts(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    runs_dir = tmp_path / "runs"
    env = os.environ.copy()
    env["RUNS_DIR"] = str(runs_dir)
    env["BROWSERBASE_API_KEY"] = ""
    env["BROWSERBASE_PROJECT_ID"] = ""
    env["BROWSERBASE_CONNECT_URL"] = ""

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "record_demo.py"),
            "--task",
            "tasks/local_checkout.json",
            "--run-id",
            "pytest_local_checkout",
            "--headless",
            "--compact",
            "--runtime",
            "local",
        ],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=True,
    )

    assert "step 1: click -> True" in result.stdout
    assert "compact step 3: crop_with_context" in result.stdout

    run_path = runs_dir / "pytest_local_checkout"
    steps = [StepRecord.model_validate(row) for row in read_jsonl(run_path / "steps.jsonl")]
    observations = [
        CompactObservation.model_validate(row)
        for row in read_jsonl(run_path / "compact_observations.jsonl")
    ]

    assert len(steps) == 4
    assert len(observations) == 4
    assert observations[0].route == "text_only"
    assert "Email is required" in observations[0].summary
    assert observations[2].route == "crop_with_context"
    assert observations[2].fallback == "crop"
    assert observations[2].crop_paths
    assert all((run_path / path).is_file() for path in observations[2].crop_paths)
    assert observations[3].route == "text_only"
    assert any(change.type == "modal_opened" for change in observations[3].changed)

    for step in steps:
        for pointer in (step.before, step.after):
            state = PageState.model_validate_json((run_path / pointer.state).read_text())
            assert state.screenshot == pointer.screenshot
            assert not Path(state.screenshot).is_absolute()
