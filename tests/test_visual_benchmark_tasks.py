from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from browserdelta.schemas import CompactObservation
from browserdelta.storage import read_jsonl


VISUAL_BENCHMARK_TASKS = [
    "visual_canvas_chart",
    "visual_progress_toast",
    "visual_swatch_picker",
]


@pytest.mark.parametrize("task_id", VISUAL_BENCHMARK_TASKS)
def test_visual_benchmark_tasks_record_and_compact(task_id: str, tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    task_path = repo_root / "tasks" / f"{task_id}.json"
    task = json.loads(task_path.read_text())
    assert len(task["actions"]) >= 3

    runs_dir = tmp_path / "runs"
    run_id = f"pytest_{task_id}"
    env = os.environ.copy()
    env["RUNS_DIR"] = str(runs_dir)
    env["BROWSERBASE_API_KEY"] = ""
    env["BROWSERBASE_PROJECT_ID"] = ""
    env["BROWSERBASE_CONNECT_URL"] = ""
    env["OPENAI_API_KEY"] = ""

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "record_demo.py"),
            "--task",
            f"tasks/{task_id}.json",
            "--run-id",
            run_id,
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

    assert "step 1: click -> True" in result.stdout

    run_path = runs_dir / run_id
    compact_path = run_path / "compact_observations.jsonl"
    assert compact_path.is_file()

    observations = [CompactObservation.model_validate(row) for row in read_jsonl(compact_path)]
    assert len(observations) >= 3
    assert _has_visual_or_meaningful_change(observations)

    if task_id == "visual_canvas_chart":
        _assert_has_crop_with_context(run_path, observations)
    elif task_id == "visual_progress_toast":
        _assert_has_crop_with_context(run_path, observations)
        assert _has_change_type(observations, "success_message")
    elif task_id == "visual_swatch_picker":
        assert _has_change_type(observations, "element_checked_changed")
        assert any(item.checked for observation in observations for item in observation.interactive)


def _has_visual_or_meaningful_change(observations: list[CompactObservation]) -> bool:
    return any(
        observation.route != "text_only"
        or observation.crop_paths
        or observation.visual_changed_pct > 1
        or observation.changed
        for observation in observations
    )


def _assert_has_crop_with_context(run_path: Path, observations: list[CompactObservation]) -> None:
    crop_observations = [
        observation
        for observation in observations
        if observation.route == "crop_with_context"
        and observation.fallback == "crop"
        and observation.crop_paths
    ]
    assert crop_observations
    for observation in crop_observations:
        assert observation.visual_changed_pct > 1
        assert all((run_path / path).is_file() for path in observation.crop_paths)


def _has_change_type(observations: list[CompactObservation], change_type: str) -> bool:
    return any(
        change.type == change_type for observation in observations for change in observation.changed
    )
