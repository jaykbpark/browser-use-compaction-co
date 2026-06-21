from __future__ import annotations

from pathlib import Path

from browserdelta.eval.runner import evaluate_comparison, evaluate_run
from browserdelta.schemas import (
    ActionResult,
    BrowserAction,
    CompactObservation,
    InteractiveElement,
    PageState,
    ReplayPrediction,
    ReplayReport,
    RunManifest,
    StatePointer,
    StepRecord,
)
from browserdelta.storage import (
    read_json,
    write_json,
    write_compact_observations,
    write_eval_report,
    write_manifest,
    write_steps,
)


def test_evaluate_run_predicts_next_actions_from_compact_observations(tmp_path: Path):
    write_manifest(
        tmp_path,
        RunManifest(
            run_id="replay_fixture",
            start_url="https://app.test",
            mode="local",
            metadata={"goal": "Use jay@example.com as the email, refresh the chart, and continue."},
        ),
    )
    write_steps(
        tmp_path,
        [
            _step(1, BrowserAction(type="click", target="Continue")),
            _step(2, BrowserAction(type="type", target="Email", text="jay@example.com")),
            _step(3, BrowserAction(type="click", target="Refresh chart")),
            _step(4, BrowserAction(type="click", target="Continue")),
        ],
    )
    write_compact_observations(
        tmp_path,
        [
            _observation(
                1,
                "New text appeared: Email is required",
                "Email is required. Current interactive elements: e1 textbox: Email; e2 button: Continue",
                [
                    InteractiveElement(ref="e1", role="textbox", name="Email"),
                    InteractiveElement(ref="e2", role="button", name="Continue"),
                ],
            ),
            _observation(
                2,
                "textbox Email value changed to jay@example.com",
                "textbox Email value changed to jay@example.com. Current interactive elements: e3 button: Refresh chart",
                [
                    InteractiveElement(
                        ref="e1", role="textbox", name="Email", value="jay@example.com"
                    ),
                    InteractiveElement(ref="e3", role="button", name="Refresh chart"),
                ],
            ),
            _observation(
                3,
                "Visual state changed by 3.3%.",
                "Visual state changed by 3.3%. Visual fallback: 4 crop(s) attached. Current interactive elements: e2 button: Continue",
                [
                    InteractiveElement(ref="e2", role="button", name="Continue"),
                    InteractiveElement(ref="e3", role="button", name="Refresh chart"),
                ],
                fallback="crop",
                route="crop_with_context",
            ),
            _observation(
                4,
                "A modal or dialog opened",
                "A modal or dialog opened.",
                [InteractiveElement(ref="e4", role="button", name="Confirm order")],
            ),
        ],
    )

    report = evaluate_run(tmp_path)

    assert report.evaluated_steps == 3
    assert report.passed_steps == 3
    assert report.next_action_accuracy == 1.0
    assert report.steps[0].predicted_next_action.type == "type"
    assert report.steps[0].predicted_next_action.text == "jay@example.com"
    assert report.steps[2].predicted_next_action.target == "Continue"
    assert (tmp_path / "eval_report.json").exists()
    ReplayReport.model_validate(read_json(tmp_path / "eval_report.json"))


def test_write_eval_report_round_trips(tmp_path: Path):
    report = ReplayReport(
        run_id="empty",
        predictor="heuristic",
        evaluated_steps=0,
        passed_steps=0,
        next_action_accuracy=0,
        compact_tokens=0,
        baseline_tokens=0,
        avg_reduction_pct=0,
    )

    write_eval_report(tmp_path, report)

    assert ReplayReport.model_validate(read_json(tmp_path / "eval_report.json")).run_id == "empty"


def test_evaluate_run_can_use_llm_predictor(tmp_path: Path, monkeypatch):
    class FakeLLMReplayAgent:
        name = "llm:fake"

        def __init__(self, **kwargs):
            pass

        def predict_next_action(
            self,
            goal: str,
            observation: CompactObservation,
            previous_action: BrowserAction | None = None,
            action_history: list[BrowserAction] | None = None,
        ) -> ReplayPrediction:
            assert goal == "Continue after the chart changes."
            assert observation.step == 1
            assert previous_action == BrowserAction(type="click", target="Refresh chart")
            assert action_history == [BrowserAction(type="click", target="Refresh chart")]
            return ReplayPrediction(
                action=BrowserAction(type="click", target="Continue"),
                rationale="The compact observation exposes the Continue button.",
                confidence=0.88,
            )

    import browserdelta.eval.runner as runner

    monkeypatch.setattr(runner, "LLMReplayAgent", FakeLLMReplayAgent)
    write_manifest(
        tmp_path,
        RunManifest(
            run_id="llm_replay_fixture",
            start_url="https://app.test",
            mode="local",
            metadata={"goal": "Continue after the chart changes."},
        ),
    )
    write_steps(
        tmp_path,
        [
            _step(1, BrowserAction(type="click", target="Refresh chart")),
            _step(2, BrowserAction(type="click", target="Continue")),
        ],
    )
    write_compact_observations(
        tmp_path,
        [
            _observation(
                1,
                "Visual state changed by 3.3%.",
                "Visual state changed. Current interactive elements: e1 button: Continue",
                [InteractiveElement(ref="e1", role="button", name="Continue")],
            )
        ],
    )

    report = evaluate_run(tmp_path, predictor="llm")

    assert report.predictor == "llm:fake"
    assert report.passed_steps == 1
    assert report.steps[0].predicted_next_action.target == "Continue"


def test_evaluate_run_resolves_interactive_refs_before_scoring(tmp_path: Path, monkeypatch):
    class FakeLLMReplayAgent:
        name = "llm:fake"

        def __init__(self, **kwargs):
            pass

        def predict_next_action(
            self,
            goal: str,
            observation: CompactObservation,
            previous_action: BrowserAction | None = None,
            action_history: list[BrowserAction] | None = None,
        ) -> ReplayPrediction:
            return ReplayPrediction(
                action=BrowserAction(type="click", target="e3"),
                rationale="Use the element ref returned by the compact observation.",
                confidence=0.82,
            )

    import browserdelta.eval.runner as runner

    monkeypatch.setattr(runner, "LLMReplayAgent", FakeLLMReplayAgent)
    write_manifest(
        tmp_path,
        RunManifest(run_id="ref_fixture", start_url="https://app.test", mode="local"),
    )
    write_steps(
        tmp_path,
        [
            _step(1, BrowserAction(type="type", target="Email", text="jay@example.com")),
            _step(2, BrowserAction(type="click", target="Refresh chart")),
        ],
    )
    write_compact_observations(
        tmp_path,
        [
            _observation(
                1,
                "textbox Email value changed to jay@example.com",
                "Current interactive elements: e3 button: Refresh chart",
                [InteractiveElement(ref="e3", role="button", name="Refresh chart")],
            )
        ],
    )

    report = evaluate_run(tmp_path, predictor="llm")

    assert report.passed_steps == 1
    assert report.steps[0].predicted_next_action.target == "Refresh chart"


def test_evaluate_run_can_score_full_state_baseline(tmp_path: Path):
    write_manifest(
        tmp_path,
        RunManifest(
            run_id="full_state_fixture",
            start_url="https://app.test",
            mode="local",
            metadata={"goal": "Use jay@example.com as the email."},
        ),
    )
    write_steps(
        tmp_path,
        [
            _step(1, BrowserAction(type="click", target="Continue")),
            _step(2, BrowserAction(type="type", target="Email", text="jay@example.com")),
        ],
    )
    _write_after_state(
        tmp_path,
        1,
        text=["Email is required"],
        interactive=[InteractiveElement(ref="e1", role="textbox", name="Email")],
    )
    _write_after_state(
        tmp_path,
        2,
        text=["Email jay@example.com"],
        interactive=[InteractiveElement(ref="e1", role="textbox", name="Email")],
    )

    report = evaluate_run(tmp_path, context_mode="full_state")

    assert report.context_mode == "full_state"
    assert report.evaluated_steps == 1
    assert report.passed_steps == 1
    assert report.steps[0].context_mode == "full_state"
    assert report.steps[0].fallback == "full_screenshot"
    assert (tmp_path / "eval_full_state_report.json").exists()
    assert not (tmp_path / "eval_report.json").exists()


def test_evaluate_run_can_score_vision_full_state_baseline(tmp_path: Path, monkeypatch):
    agent_configs: list[dict] = []

    class FakeLLMReplayAgent:
        name = "llm-vision:fake"

        def __init__(self, **kwargs):
            agent_configs.append(kwargs)

        def predict_next_action(
            self,
            goal: str,
            observation: CompactObservation,
            previous_action: BrowserAction | None = None,
            action_history: list[BrowserAction] | None = None,
        ) -> ReplayPrediction:
            assert observation.full_screenshot_path == "steps/step_001_after.png"
            return ReplayPrediction(
                action=BrowserAction(type="type", target="Email", text="jay@example.com"),
                rationale="The screenshot and full state show the email field.",
                confidence=0.84,
            )

    import browserdelta.eval.runner as runner

    monkeypatch.setattr(runner, "LLMReplayAgent", FakeLLMReplayAgent)
    write_manifest(
        tmp_path,
        RunManifest(
            run_id="vision_full_state_fixture",
            start_url="https://app.test",
            mode="local",
            metadata={"goal": "Use jay@example.com as the email."},
        ),
    )
    write_steps(
        tmp_path,
        [
            _step(1, BrowserAction(type="click", target="Continue")),
            _step(2, BrowserAction(type="type", target="Email", text="jay@example.com")),
        ],
    )
    _write_after_state(
        tmp_path,
        1,
        text=["Email is required"],
        interactive=[InteractiveElement(ref="e1", role="textbox", name="Email")],
    )
    _write_after_state(
        tmp_path,
        2,
        text=["Email jay@example.com"],
        interactive=[InteractiveElement(ref="e1", role="textbox", name="Email")],
    )

    report = evaluate_run(tmp_path, predictor="llm", context_mode="vision_full_state")

    assert report.context_mode == "vision_full_state"
    assert report.passed_steps == 1
    assert agent_configs == [{"artifact_root": tmp_path, "include_images": True}]
    assert (tmp_path / "eval_vision_full_state_report.json").exists()


def test_evaluate_comparison_writes_json_and_readable_summary(tmp_path: Path):
    write_manifest(
        tmp_path,
        RunManifest(
            run_id="comparison_fixture",
            start_url="https://app.test",
            mode="local",
            metadata={"goal": "Use jay@example.com as the email."},
        ),
    )
    write_steps(
        tmp_path,
        [
            _step(1, BrowserAction(type="click", target="Continue")),
            _step(2, BrowserAction(type="type", target="Email", text="jay@example.com")),
        ],
    )
    write_compact_observations(
        tmp_path,
        [
            _observation(
                1,
                "Email is required",
                "Email is required. Current interactive elements: e1 textbox: Email",
                [InteractiveElement(ref="e1", role="textbox", name="Email")],
            )
        ],
    )
    _write_after_state(
        tmp_path,
        1,
        text=["Email is required"],
        interactive=[InteractiveElement(ref="e1", role="textbox", name="Email")],
    )
    _write_after_state(
        tmp_path,
        2,
        text=["Email jay@example.com"],
        interactive=[InteractiveElement(ref="e1", role="textbox", name="Email")],
    )

    report = evaluate_comparison(tmp_path, predictor="heuristic")

    assert report.summary.compact_passed_steps == 1
    assert report.summary.baseline_passed_steps == 1
    assert report.summary.token_reduction_pct > 0
    assert report.verdict == "compact_matches_or_beats_baseline"
    assert (tmp_path / "eval_report.json").exists()
    assert report.summary.baseline_context_mode == "vision_full_state"
    assert (tmp_path / "eval_vision_full_state_report.json").exists()
    assert (tmp_path / "eval_comparison.json").exists()
    summary_text = (tmp_path / "eval_summary.md").read_text()
    assert "Plain English" in summary_text
    assert "Vision full state baseline accuracy" in summary_text


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
            url="https://app.test",
            title="App",
            text=text,
            interactive=interactive,
            screenshot=f"steps/step_{step:03d}_after.png",
        ),
    )


def _observation(
    step: int,
    summary: str,
    llm_observation: str,
    interactive: list[InteractiveElement],
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
        tokens_estimate=20,
        baseline_tokens_estimate=500,
        reduction_pct=80,
    )
