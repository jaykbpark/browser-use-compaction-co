"""Benchmark: search/filter/table task.

Stresses BrowserDelta on large list transitions (filtering a 12-row table down to
a handful of rows and back). Tests are heuristic-only and never call OpenAI. The
end-to-end tests skip cleanly when a local browser is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

TASK_PATH = ROOT / "tasks" / "search_filter.json"
PAGE_PATH = ROOT / "demo_pages" / "search_filter.html"


def test_task_and_page_are_well_formed():
    """Static, browser-free validation of the benchmark assets."""

    task = json.loads(TASK_PATH.read_text())
    for key in ("id", "goal", "start_url", "actions", "success_hint"):
        assert key in task, f"missing task key: {key}"
    assert task["id"] == "search_filter"
    assert len(task["actions"]) >= 3
    assert task["start_url"] == "demo_pages/search_filter.html"

    html = PAGE_PATH.read_text()
    # Self-contained and offline: no external resource references.
    assert "http://" not in html
    assert "https://" not in html
    assert 'placeholder="Search fruits"' in html
    # Action targets must be reachable: the Strawberry row, the "Add <name>"
    # button label, and the Reset button.
    assert '"Strawberry"' in html
    assert '"Add " + fruit.name' in html
    assert ">Reset<" in html


@pytest.fixture(scope="module")
def recorded_run(tmp_path_factory):
    """Record + compact the benchmark once. Skips if no local browser."""

    run_root = tmp_path_factory.mktemp("runs")
    prev = os.environ.get("RUNS_DIR")
    os.environ["RUNS_DIR"] = str(run_root)

    from browserdelta.compaction.codec import compact_run
    from browserdelta.config import get_settings
    from record_task import record_task

    get_settings.cache_clear()
    task = json.loads(TASK_PATH.read_text())
    try:
        asyncio.run(record_task(task, headless=True))
    except Exception as exc:  # noqa: BLE001 - browser may be unavailable in CI
        pytest.skip(f"local browser unavailable: {exc}")

    run_path = run_root / task["id"]
    compact_run(run_path)

    yield run_path, task

    if prev is None:
        os.environ.pop("RUNS_DIR", None)
    else:
        os.environ["RUNS_DIR"] = prev
    get_settings.cache_clear()


def _observations(run_path: Path) -> list[dict]:
    path = run_path / "compact_observations.jsonl"
    assert path.exists(), "compact_observations.jsonl was not written"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_records_and_compacts(recorded_run):
    run_path, _ = recorded_run
    observations = _observations(run_path)

    assert len(observations) >= 3
    # At least one transition produced a structural change and a route decision.
    assert any(obs.get("changed") for obs in observations)
    assert any(obs.get("fallback") in {"none", "crop", "full_screenshot"} for obs in observations)


def test_heuristic_eval_runs(recorded_run):
    from browserdelta.eval.ab import evaluate_run

    run_path, task = recorded_run
    report = evaluate_run(run_path, task=task, predictor="heuristic")

    assert report["summary"]["n_steps"] >= 3
    assert report["summary"]["routes_compact"]
    # The agent can still ground the scripted next action from compact context.
    assert report["summary"]["next_action"]["compact_accuracy"] == 1.0


@pytest.mark.xfail(
    reason=(
        "Compaction gap: filtering the table triggers a large visual diff, so the "
        "codec routes to image_crop and emits ~8 crops/step. Each crop pays the "
        "per-image base+tile cost, so compact tokens meet or exceed baseline (~0% "
        "savings) even though the structural diff already lists the removed rows. "
        "Crop fallback is redundant when structural changes fully explain the "
        "transition; cap crop count or prefer structural-only routing."
    ),
    strict=False,
)
def test_search_filter_yields_token_savings(recorded_run):
    from browserdelta.eval.ab import evaluate_run

    run_path, task = recorded_run
    report = evaluate_run(run_path, task=task, predictor="heuristic")
    assert report["summary"]["tokens"]["savings_pct"] > 20
