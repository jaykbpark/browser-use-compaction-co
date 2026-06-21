from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path

from browserdelta.schemas import CompactObservation
from browserdelta.storage import read_jsonl


def test_search_filter_task_records_compacts_and_evaluates(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    runs_dir = tmp_path / "runs"
    env = os.environ.copy()
    env["RUNS_DIR"] = str(runs_dir)
    env["BROWSERBASE_API_KEY"] = ""
    env["BROWSERBASE_PROJECT_ID"] = ""
    env["BROWSERBASE_CONNECT_URL"] = ""
    env["OPENAI_API_KEY"] = ""

    record = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "record_demo.py"),
            "--task",
            "tasks/search_filter.json",
            "--run-id",
            "pytest_search_filter",
            "--headless",
            "--compact",
            "--runtime",
            "local",
        ],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=90,
        check=True,
    )

    assert "step 1: type -> True" in record.stdout
    run_path = runs_dir / "pytest_search_filter"
    observations = [
        CompactObservation.model_validate(row)
        for row in read_jsonl(run_path / "compact_observations.jsonl")
    ]
    assert len(observations) == 4
    assert any("Strawberry" in item.name for obs in observations for item in obs.interactive)
    assert any(obs.reduction_pct > 0 for obs in observations)

    eval_result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "eval_run.py"),
            str(run_path),
            "--goal",
            "Filter the fruit table and add strawberry.",
        ],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    )
    assert "replay eval:" in eval_result.stdout
    report = json.loads((run_path / "eval_report.json").read_text())
    assert report["evaluated_steps"] == 3
    assert report["passed_steps"] >= 1
