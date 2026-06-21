from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from browserdelta.compaction.image_diff import diff_images
from browserdelta.compaction.codec import compact_run


@pytest.mark.parametrize(
    ("fixture_name", "expected_route", "expected_fallback", "expected_summary"),
    [
        ("login_error", "text_only", "none", "Email is required"),
        ("modal_checkout", "text_only", "none", "modal or dialog opened"),
        ("visual_only_change", "crop_with_context", "crop", "Visual state changed"),
    ],
)
def test_example_fixtures_compact_to_expected_routes(
    tmp_path: Path,
    fixture_name: str,
    expected_route: str,
    expected_fallback: str,
    expected_summary: str,
):
    fixture = Path(__file__).resolve().parents[1] / "examples" / "runs" / fixture_name
    run_copy = tmp_path / fixture_name
    shutil.copytree(fixture, run_copy)

    observations = compact_run(run_copy)

    assert len(observations) == 1
    observation = observations[0]
    assert observation.route == expected_route
    assert observation.fallback == expected_fallback
    assert expected_summary in observation.summary
    assert observation.reduction_pct > 0
    assert (run_copy / "compact_observations.jsonl").exists()

    if expected_fallback == "crop":
        assert observation.crop_paths
        assert all(not Path(path).is_absolute() for path in observation.crop_paths)
        assert all((run_copy / path).exists() for path in observation.crop_paths)
        assert "Visual fallback" in observation.llm_observation
    else:
        assert observation.confidence > 0.85
        assert observation.crop_paths == []


@pytest.mark.parametrize(
    ("fixture_name", "min_changed_pct", "max_changed_pct"),
    [
        ("login_error", 1.0, 15.0),
        ("modal_checkout", 1.0, 15.0),
        ("visual_only_change", 1.0, 15.0),
    ],
)
def test_example_fixture_images_have_meaningful_bounded_diffs(
    fixture_name: str,
    min_changed_pct: float,
    max_changed_pct: float,
):
    steps = Path(__file__).resolve().parents[1] / "examples" / "runs" / fixture_name / "steps"
    visual = diff_images(steps / "step_001_before.png", steps / "step_001_after.png")

    assert min_changed_pct <= visual.changed_pct <= max_changed_pct
    assert visual.regions
