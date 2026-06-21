from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from browserdelta.compaction.codec import compact_run
from browserdelta.schemas import (
    ActionResult,
    BrowserAction,
    CompactObservation,
    PageState,
    RunManifest,
    StatePointer,
    StepRecord,
)
from browserdelta.storage import (
    read_jsonl,
    read_manifest,
    read_steps,
    write_json,
    write_manifest,
    write_steps,
)


def test_example_runs_follow_recorder_compaction_file_contract():
    repo_root = Path(__file__).resolve().parents[1]
    fixtures_root = repo_root / "examples" / "runs"

    for run_path in fixtures_root.iterdir():
        if not run_path.is_dir():
            continue

        manifest = read_manifest(run_path)
        steps = read_steps(run_path)

        assert manifest.steps_path == "steps.jsonl"
        assert steps, f"{run_path.name} should contain at least one step"

        for step in steps:
            for pointer in (step.before, step.after):
                assert not Path(pointer.screenshot).is_absolute()
                assert not Path(pointer.state).is_absolute()
                assert (run_path / pointer.screenshot).is_file()
                assert (run_path / pointer.state).is_file()
                state = PageState.model_validate_json((run_path / pointer.state).read_text())
                if state.screenshot:
                    assert not Path(state.screenshot).is_absolute()


def test_manifest_steps_path_is_honored_end_to_end(tmp_path: Path):
    steps_dir = tmp_path / "steps"
    steps_dir.mkdir()
    before_png = steps_dir / "step_001_before.png"
    after_png = steps_dir / "step_001_after.png"
    Image.new("RGB", (100, 100), "white").save(before_png)
    Image.new("RGB", (100, 100), "white").save(after_png)

    state = PageState(url="https://app.test", title="Test", text=["Ready"])
    write_json(steps_dir / "step_001_before.json", state)
    write_json(steps_dir / "step_001_after.json", state)

    step = StepRecord(
        step=1,
        action=BrowserAction(type="click", target="Ready"),
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
    write_manifest(
        tmp_path,
        RunManifest(
            run_id="custom_steps",
            start_url="https://app.test",
            mode="local",
            steps_path="records/custom_steps.jsonl",
        ),
    )
    write_steps(tmp_path, [step])

    assert (tmp_path / "records" / "custom_steps.jsonl").is_file()
    assert not (tmp_path / "steps.jsonl").exists()
    assert read_steps(tmp_path)[0].step == 1

    observations = compact_run(tmp_path)

    assert len(observations) == 1
    assert (tmp_path / "compact_observations.jsonl").is_file()
    rows = read_jsonl(tmp_path / "compact_observations.jsonl")
    CompactObservation.model_validate(rows[0])


def test_compact_run_writes_run_relative_crop_paths(tmp_path: Path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    fixture = repo_root / "examples" / "runs" / "visual_only_change"
    shutil.copytree(fixture, tmp_path / "visual_only_change")

    monkeypatch.chdir(tmp_path)
    run_path = Path("visual_only_change")
    observation = compact_run(run_path)[0]

    assert observation.crop_paths
    assert all(not Path(path).is_absolute() for path in observation.crop_paths)
    assert all(not path.startswith("visual_only_change/") for path in observation.crop_paths)
    assert all((run_path / path).is_file() for path in observation.crop_paths)
