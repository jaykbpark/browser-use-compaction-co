from __future__ import annotations

import json
import importlib.util
from pathlib import Path

from browserdelta.schemas import (
    ActionResult,
    BrowserAction,
    CompactObservation,
    EvalComparisonReport,
    EvalComparisonSummary,
    InteractiveElement,
    ReplayReport,
    RunManifest,
    StatePointer,
    StepRecord,
)
from browserdelta.storage import write_compact_observations, write_manifest, write_steps


def _load_eval_suite_module():
    repo_root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("eval_suite", repo_root / "scripts/eval_suite.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


eval_suite = _load_eval_suite_module()


def test_evaluate_suite_aggregates_tiny_fake_runs(tmp_path: Path):
    validation_run = tmp_path / "validation"
    visual_run = tmp_path / "visual"
    _write_validation_run(validation_run, run_id="validation", reduction_pct=80)
    _write_visual_run(visual_run, run_id="visual", reduction_pct=60)

    suite = eval_suite.evaluate_suite([validation_run, visual_run], predictor="heuristic")

    assert suite["predictor"] == "heuristic"
    assert suite["runs"] == [
        {
            "run_id": "validation",
            "predictor": "heuristic",
            "passed": 1,
            "evaluated": 1,
            "passed_evaluated": "1/1",
            "accuracy": 1.0,
            "avg_reduction_pct": 80.0,
            "compact_tokens": 20,
            "baseline_tokens": 100,
        },
        {
            "run_id": "visual",
            "predictor": "heuristic",
            "passed": 1,
            "evaluated": 1,
            "passed_evaluated": "1/1",
            "accuracy": 1.0,
            "avg_reduction_pct": 60.0,
            "compact_tokens": 30,
            "baseline_tokens": 75,
        },
    ]
    assert suite["summary"] == {
        "runs": 2,
        "passed": 2,
        "evaluated": 2,
        "passed_evaluated": "2/2",
        "accuracy": 1.0,
        "avg_reduction_pct": 70.0,
        "compact_tokens": 50,
        "baseline_tokens": 175,
    }


def test_eval_suite_json_output_accepts_task_files(tmp_path: Path, monkeypatch, capsys):
    runs_root = tmp_path / "runs"
    run_path = runs_root / "checkout_task"
    run_path.mkdir(parents=True)
    task_path = tmp_path / "checkout_task.json"
    task_path.write_text(
        json.dumps(
            {
                "id": "checkout_task",
                "goal": "Finish checkout.",
                "start_url": "demo_pages/local_checkout.html",
                "actions": [{"type": "click", "target": "Continue"}],
            }
        )
    )
    calls: list[tuple[Path, str | None, str]] = []

    def fake_evaluate_run(
        path: Path,
        goal: str | None = None,
        predictor: str = "heuristic",
        **_kwargs,
    ) -> ReplayReport:
        calls.append((path, goal, predictor))
        return ReplayReport(
            run_id=path.name,
            predictor="llm:fake",
            evaluated_steps=2,
            passed_steps=1,
            next_action_accuracy=0.5,
            compact_tokens=40,
            baseline_tokens=100,
            avg_reduction_pct=60,
        )

    monkeypatch.setattr(eval_suite, "ROOT", tmp_path)
    monkeypatch.setattr(eval_suite, "evaluate_run", fake_evaluate_run)

    assert eval_suite.main(["--predictor", "llm", "--json", str(task_path)]) == 0

    output = json.loads(capsys.readouterr().out)
    assert calls == [(run_path, "Finish checkout.", "llm")]
    assert output["runs"][0]["run_id"] == "checkout_task"
    assert output["runs"][0]["predictor"] == "llm:fake"
    assert output["summary"]["passed_evaluated"] == "1/2"


def test_eval_suite_compare_mode_aggregates_compact_vs_full_state(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    runs_root = tmp_path / "runs"
    run_path = runs_root / "checkout_task"
    run_path.mkdir(parents=True)
    task_path = tmp_path / "checkout_task.json"
    task_path.write_text(
        json.dumps(
            {
                "id": "checkout_task",
                "goal": "Finish checkout.",
                "start_url": "demo_pages/local_checkout.html",
                "actions": [{"type": "click", "target": "Continue"}],
            }
        )
    )
    calls: list[tuple[Path, str | None, str, str]] = []

    def fake_evaluate_comparison(
        path: Path,
        goal: str | None = None,
        predictor: str = "heuristic",
        baseline_context_mode: str = "vision_full_state",
        **_kwargs,
    ) -> EvalComparisonReport:
        calls.append((path, goal, predictor, baseline_context_mode))
        compact = ReplayReport(
            run_id=path.name,
            predictor="llm:fake",
            context_mode="compact",
            evaluated_steps=2,
            passed_steps=2,
            next_action_accuracy=1.0,
            compact_tokens=40,
            baseline_tokens=100,
            avg_reduction_pct=60,
        )
        baseline = ReplayReport(
            run_id=path.name,
            predictor="llm:fake",
            context_mode="vision_full_state",
            evaluated_steps=2,
            passed_steps=1,
            next_action_accuracy=0.5,
            compact_tokens=100,
            baseline_tokens=100,
            avg_reduction_pct=0,
        )
        summary = EvalComparisonSummary(
            run_id=path.name,
            predictor="llm:fake",
            baseline_context_mode="vision_full_state",
            evaluated_steps=2,
            compact_passed_steps=2,
            baseline_passed_steps=1,
            compact_accuracy=1.0,
            baseline_accuracy=0.5,
            accuracy_delta=0.5,
            compact_tokens=40,
            baseline_tokens=100,
            token_savings=60,
            token_reduction_pct=60,
        )
        return EvalComparisonReport(
            run_id=path.name,
            predictor="llm:fake",
            compact=compact,
            baseline=baseline,
            summary=summary,
            verdict="compact_matches_or_beats_baseline",
            explanation=["Compact matched the task with fewer tokens."],
        )

    monkeypatch.setattr(eval_suite, "ROOT", tmp_path)
    monkeypatch.setattr(eval_suite, "evaluate_comparison", fake_evaluate_comparison)

    assert eval_suite.main(["--predictor", "llm", "--compare", "--json", str(task_path)]) == 0

    output = json.loads(capsys.readouterr().out)
    assert calls == [(run_path, "Finish checkout.", "llm", "vision_full_state")]
    assert output["mode"] == "comparison"
    assert output["baseline_context_mode"] == "vision_full_state"
    assert output["runs"][0]["compact_passed_evaluated"] == "2/2"
    assert output["runs"][0]["baseline_passed_evaluated"] == "1/2"
    assert output["runs"][0]["baseline_context_mode"] == "vision_full_state"
    assert output["summary"]["token_reduction_pct"] == 60


def test_format_table_includes_run_rows_and_total():
    suite = {
        "predictor": "heuristic",
        "runs": [
            {
                "run_id": "run_one",
                "predictor": "heuristic",
                "passed": 1,
                "evaluated": 2,
                "passed_evaluated": "1/2",
                "accuracy": 0.5,
                "avg_reduction_pct": 25.5,
                "compact_tokens": 10,
                "baseline_tokens": 40,
            }
        ],
        "summary": {
            "runs": 1,
            "passed": 1,
            "evaluated": 2,
            "passed_evaluated": "1/2",
            "accuracy": 0.5,
            "avg_reduction_pct": 25.5,
            "compact_tokens": 10,
            "baseline_tokens": 40,
        },
    }

    table = eval_suite.format_table(suite)

    assert "run_id" in table
    assert "passed/evaluated" in table
    assert "run_one" in table
    assert "TOTAL" in table
    assert "50.0%" in table
    assert "25.50%" in table


def test_format_table_includes_comparison_columns():
    suite = {
        "predictor": "llm",
        "mode": "comparison",
        "runs": [
            {
                "run_id": "run_one",
                "predictor": "llm:fake",
                "compact_passed_evaluated": "2/2",
                "baseline_passed_evaluated": "1/2",
                "baseline_context_mode": "vision_full_state",
                "token_reduction_pct": 60,
                "compact_tokens": 40,
                "baseline_tokens": 100,
                "verdict": "compact_matches_or_beats_baseline",
            }
        ],
        "summary": {
            "runs": 1,
            "baseline_context_mode": "vision_full_state",
            "compact_passed": 2,
            "baseline_passed": 1,
            "evaluated": 2,
            "compact_passed_evaluated": "2/2",
            "baseline_passed_evaluated": "1/2",
            "compact_accuracy": 1.0,
            "baseline_accuracy": 0.5,
            "accuracy_delta": 0.5,
            "token_reduction_pct": 60,
            "token_savings": 60,
            "compact_tokens": 40,
            "baseline_tokens": 100,
        },
    }

    table = eval_suite.format_table(suite)

    assert "compact" in table
    assert "baseline_context" in table
    assert "vision_full_state" in table
    assert "run_one" in table
    assert "60.00%" in table
    assert "TOTAL" in table


def _write_validation_run(run_path: Path, run_id: str, reduction_pct: float) -> None:
    write_manifest(
        run_path,
        RunManifest(
            run_id=run_id,
            start_url="https://app.test",
            mode="local",
            metadata={"goal": "Use jay@example.com as the email."},
        ),
    )
    write_steps(
        run_path,
        [
            _step(1, BrowserAction(type="click", target="Continue")),
            _step(2, BrowserAction(type="type", target="Email", text="jay@example.com")),
        ],
    )
    write_compact_observations(
        run_path,
        [
            _observation(
                1,
                "Email is required",
                "Email is required. Current interactive elements: e1 textbox: Email",
                [InteractiveElement(ref="e1", role="textbox", name="Email")],
                compact_tokens=20,
                baseline_tokens=100,
                reduction_pct=reduction_pct,
            )
        ],
    )


def _write_visual_run(run_path: Path, run_id: str, reduction_pct: float) -> None:
    write_manifest(
        run_path,
        RunManifest(
            run_id=run_id,
            start_url="https://app.test",
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
            _observation(
                1,
                "Visual state changed by 3.3%.",
                "Visual fallback: crop attached. Current interactive elements: e2 button: Continue",
                [InteractiveElement(ref="e2", role="button", name="Continue")],
                compact_tokens=30,
                baseline_tokens=75,
                reduction_pct=reduction_pct,
                fallback="crop",
                route="crop_with_context",
            )
        ],
    )


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


def _observation(
    step: int,
    summary: str,
    llm_observation: str,
    interactive: list[InteractiveElement],
    compact_tokens: int,
    baseline_tokens: int,
    reduction_pct: float,
    fallback: str = "none",
    route: str = "text_only",
) -> CompactObservation:
    return CompactObservation(
        step=step,
        action_result="success",
        summary=summary,
        llm_observation=llm_observation,
        interactive=interactive,
        fallback=fallback,  # type: ignore[arg-type]
        route=route,  # type: ignore[arg-type]
        tokens_estimate=compact_tokens,
        baseline_tokens_estimate=baseline_tokens,
        reduction_pct=reduction_pct,
    )
