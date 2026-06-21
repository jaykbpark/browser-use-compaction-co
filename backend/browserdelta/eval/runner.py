from __future__ import annotations

from pathlib import Path

from browserdelta.compaction.codec import compact_run
from browserdelta.compaction.metrics import estimate_raw_baseline_tokens, estimate_text_tokens
from browserdelta.eval.agent_judge import HeuristicReplayAgent, actions_match
from browserdelta.eval.llm_agent import LLMReplayAgent
from browserdelta.observability.arize import ArizeEvalTracer, noop_arize_tracer
from browserdelta.schemas import (
    BrowserAction,
    CompactObservation,
    EvalComparisonReport,
    EvalComparisonSummary,
    InteractiveElement,
    PageState,
    ReplayContextMode,
    ReplayReport,
    ReplayStepResult,
    RunManifest,
    StepRecord,
)
from browserdelta.storage import (
    read_json,
    read_jsonl,
    read_manifest,
    read_steps,
    write_eval_comparison_report,
    write_eval_report,
)

_CONTEXT_MODES: set[ReplayContextMode] = {"compact", "full_state", "vision_full_state"}


def evaluate_run(
    run_path: Path,
    goal: str | None = None,
    predictor: str = "heuristic",
    context_mode: ReplayContextMode = "compact",
    write_report: bool = True,
    arize_tracer: ArizeEvalTracer | None = None,
) -> ReplayReport:
    if context_mode not in _CONTEXT_MODES:
        raise ValueError(
            "Unknown context_mode. Expected compact, full_state, or vision_full_state."
        )

    steps = read_steps(run_path)
    observations = _read_observations(run_path, steps, context_mode)
    observations_by_step = {observation.step: observation for observation in observations}
    manifest = _read_manifest_if_present(run_path)
    effective_goal = goal or _goal_from_manifest(manifest)
    run_id = manifest.run_id if manifest else run_path.name
    trace = arize_tracer or noop_arize_tracer()

    agent = _make_agent(predictor, context_mode=context_mode, run_path=run_path)
    results: list[ReplayStepResult] = []

    with trace.run_span(
        run_id=run_id,
        run_path=run_path,
        predictor=predictor,
        context_mode=context_mode,
        goal=effective_goal,
    ) as run_span:
        for index, step in enumerate(steps[:-1]):
            observation = observations_by_step.get(step.step)
            if observation is None:
                continue

            expected_next_action = steps[index + 1].action
            with trace.step_span(
                run_id=run_id,
                context_mode=context_mode,
                step=step.step,
                observation=observation,
                expected_next_action=expected_next_action,
                previous_action=step.action,
            ) as step_span:
                prediction = agent.predict_next_action(
                    effective_goal,
                    observation,
                    previous_action=step.action,
                    action_history=[record.action for record in steps[: index + 1]],
                )
                predicted_action = _resolve_target_alias(prediction.action, observation)
                passed, reason = actions_match(predicted_action, expected_next_action)

                result = ReplayStepResult(
                    step=step.step,
                    context_mode=context_mode,
                    observation_summary=observation.summary,
                    expected_next_action=expected_next_action,
                    predicted_next_action=predicted_action,
                    passed=passed,
                    match_reason=reason,
                    rationale=prediction.rationale,
                    confidence=prediction.confidence,
                    route=observation.route,
                    fallback=observation.fallback,
                    tokens_estimate=observation.tokens_estimate,
                    baseline_tokens_estimate=observation.baseline_tokens_estimate,
                    reduction_pct=observation.reduction_pct,
                )
                trace.record_step(step_span, result)
                results.append(result)

        report = ReplayReport(
            run_id=run_id,
            predictor=agent.name,
            context_mode=context_mode,
            evaluated_steps=len(results),
            passed_steps=sum(1 for result in results if result.passed),
            next_action_accuracy=_accuracy(results),
            compact_tokens=sum(result.tokens_estimate for result in results),
            baseline_tokens=sum(result.baseline_tokens_estimate for result in results),
            avg_reduction_pct=_avg_reduction(results),
            steps=results,
        )
        trace.record_report(run_span, report)

        if write_report:
            write_eval_report(run_path, report)
        return report


def evaluate_comparison(
    run_path: Path,
    goal: str | None = None,
    predictor: str = "llm",
    baseline_context_mode: ReplayContextMode = "vision_full_state",
    write_report: bool = True,
    arize_tracer: ArizeEvalTracer | None = None,
) -> EvalComparisonReport:
    if baseline_context_mode == "compact":
        raise ValueError(
            "Comparison baseline_context_mode must be full_state or vision_full_state."
        )
    if baseline_context_mode not in _CONTEXT_MODES:
        raise ValueError("Unknown baseline_context_mode. Expected full_state or vision_full_state.")

    trace = arize_tracer or noop_arize_tracer()
    manifest = _read_manifest_if_present(Path(run_path))
    effective_goal = goal or _goal_from_manifest(manifest)
    with trace.comparison_span(
        run_path=run_path,
        predictor=predictor,
        baseline_context_mode=baseline_context_mode,
        goal=effective_goal,
    ) as comparison_span:
        compact = evaluate_run(
            run_path,
            goal=goal,
            predictor=predictor,
            context_mode="compact",
            write_report=write_report,
            arize_tracer=trace,
        )
        baseline = evaluate_run(
            run_path,
            goal=goal,
            predictor=predictor,
            context_mode=baseline_context_mode,
            write_report=write_report,
            arize_tracer=trace,
        )
        summary = _comparison_summary(compact, baseline)
        report = EvalComparisonReport(
            run_id=compact.run_id,
            predictor=compact.predictor,
            compact=compact,
            baseline=baseline,
            summary=summary,
            verdict=_comparison_verdict(summary),
            explanation=_comparison_explanation(summary),
        )
        trace.record_comparison(comparison_span, report)
        if write_report:
            write_eval_comparison_report(run_path, report)
            _write_eval_summary_markdown(run_path, report)
        return report


def _read_observations(
    run_path: Path,
    steps: list[StepRecord],
    context_mode: ReplayContextMode,
) -> list[CompactObservation]:
    if context_mode in {"full_state", "vision_full_state"}:
        return _baseline_observations(run_path, steps, context_mode=context_mode)
    return _read_or_compact_observations(run_path)


def _read_or_compact_observations(run_path: Path) -> list[CompactObservation]:
    rows = read_jsonl(run_path / "compact_observations.jsonl")
    if not rows:
        return compact_run(run_path)
    return [CompactObservation.model_validate(row) for row in rows]


def _baseline_observations(
    run_path: Path,
    steps: list[StepRecord],
    context_mode: ReplayContextMode,
) -> list[CompactObservation]:
    observations: list[CompactObservation] = []
    for step in steps:
        after_state = PageState.model_validate(read_json(run_path / step.after.state))
        baseline_tokens = estimate_raw_baseline_tokens(
            after_state, run_path / step.after.screenshot
        )
        llm_observation = _render_full_state_observation(
            after_state,
            step.after.screenshot,
            context_mode=context_mode,
        )
        observations.append(
            CompactObservation(
                step=step.step,
                action_result="success" if step.result.ok else "failed",
                summary=f"{_context_label(context_mode)} after {step.action.type}.",
                changed=[],
                interactive=after_state.interactive,
                fallback="full_screenshot",
                route="full_screenshot",
                route_reason=_baseline_route_reason(context_mode),
                confidence=1.0,
                llm_observation=llm_observation,
                crop_paths=[],
                full_screenshot_path=step.after.screenshot,
                tokens_estimate=max(baseline_tokens, estimate_text_tokens(llm_observation)),
                baseline_tokens_estimate=baseline_tokens,
                reduction_pct=0.0,
            )
        )
    return observations


def _render_full_state_observation(
    after_state: PageState,
    screenshot_path: str,
    context_mode: ReplayContextMode,
) -> str:
    screenshot_hint = (
        f"{screenshot_path} (attached as input_image)"
        if context_mode == "vision_full_state"
        else screenshot_path
    )
    lines = [
        f"{_context_label(context_mode).upper()} BASELINE CONTEXT",
        f"URL: {after_state.url}",
        f"Title: {after_state.title or '(none)'}",
        f"Screenshot: {screenshot_hint}",
    ]
    if after_state.text:
        lines.append("Visible text:")
        lines.extend(f"- {line}" for line in after_state.text)
    if after_state.interactive:
        lines.append("Current interactive elements:")
        lines.extend(_render_full_state_interactive(item) for item in after_state.interactive)
    if after_state.focused_ref:
        lines.append(f"Focused element ref: {after_state.focused_ref}")
    if after_state.console_errors:
        lines.append("Console errors:")
        lines.extend(f"- {error}" for error in after_state.console_errors)
    if after_state.network_errors:
        lines.append("Network errors:")
        lines.extend(f"- {error}" for error in after_state.network_errors)
    return "\n".join(lines)


def _render_full_state_interactive(item: InteractiveElement) -> str:
    attrs = item.attributes or {}
    attrs_text = ", ".join(f"{key}={value}" for key, value in attrs.items() if value)
    state_bits = []
    for field in ("value", "disabled", "checked", "selected", "expanded"):
        value = getattr(item, field)
        if value is not None:
            state_bits.append(f"{field}={value}")
    suffix = f" ({'; '.join(state_bits)})" if state_bits else ""
    attrs_suffix = f" attrs[{attrs_text}]" if attrs_text else ""
    return f"- {item.ref} {item.role}: {item.name or item.value or item.ref}{suffix}{attrs_suffix}"


def _make_agent(
    predictor: str,
    context_mode: ReplayContextMode,
    run_path: Path,
) -> HeuristicReplayAgent | LLMReplayAgent:
    if predictor == "heuristic":
        return HeuristicReplayAgent()
    if predictor == "llm":
        return LLMReplayAgent(
            artifact_root=run_path,
            include_images=context_mode == "vision_full_state",
        )
    raise ValueError(f"Unknown predictor {predictor!r}. Expected heuristic or llm.")


def _comparison_summary(
    compact: ReplayReport,
    baseline: ReplayReport,
) -> EvalComparisonSummary:
    compact_tokens = compact.compact_tokens
    baseline_tokens = baseline.baseline_tokens or baseline.compact_tokens
    return EvalComparisonSummary(
        run_id=compact.run_id,
        predictor=compact.predictor,
        baseline_context_mode=baseline.context_mode,
        evaluated_steps=min(compact.evaluated_steps, baseline.evaluated_steps),
        compact_passed_steps=compact.passed_steps,
        baseline_passed_steps=baseline.passed_steps,
        compact_accuracy=compact.next_action_accuracy,
        baseline_accuracy=baseline.next_action_accuracy,
        accuracy_delta=round(compact.next_action_accuracy - baseline.next_action_accuracy, 3),
        compact_tokens=compact_tokens,
        baseline_tokens=baseline_tokens,
        token_savings=max(0, baseline_tokens - compact_tokens),
        token_reduction_pct=_token_reduction_pct(baseline_tokens, compact_tokens),
    )


def _comparison_verdict(summary: EvalComparisonSummary) -> str:
    if summary.compact_accuracy >= summary.baseline_accuracy and summary.token_reduction_pct > 0:
        return "compact_matches_or_beats_baseline"
    if summary.compact_accuracy == summary.baseline_accuracy:
        return "compact_matches_baseline_accuracy"
    return "compact_loses_accuracy"


def _comparison_explanation(summary: EvalComparisonSummary) -> list[str]:
    return [
        (
            f"Compact context got {summary.compact_passed_steps}/{summary.evaluated_steps} "
            f"next actions correct."
        ),
        (
            f"{_context_label(summary.baseline_context_mode)} baseline got "
            f"{summary.baseline_passed_steps}/{summary.evaluated_steps} "
            f"next actions correct."
        ),
        (
            f"Compact context used {summary.compact_tokens} estimated tokens versus "
            f"{summary.baseline_tokens} for {_context_label(summary.baseline_context_mode)}, "
            f"saving {summary.token_reduction_pct:.2f}%."
        ),
    ]


def _write_eval_summary_markdown(run_path: Path, report: EvalComparisonReport) -> None:
    summary = report.summary
    lines = [
        f"# BrowserDelta Eval: {report.run_id}",
        "",
        "## Result",
        "",
        f"- Verdict: `{report.verdict}`",
        f"- Predictor: `{report.predictor}`",
        f"- Compact next-action accuracy: {summary.compact_passed_steps}/{summary.evaluated_steps} ({summary.compact_accuracy * 100:.1f}%)",
        f"- {_context_label(summary.baseline_context_mode)} baseline accuracy: {summary.baseline_passed_steps}/{summary.evaluated_steps} ({summary.baseline_accuracy * 100:.1f}%)",
        f"- Estimated token savings: {summary.token_savings} tokens ({summary.token_reduction_pct:.2f}%)",
        "",
        "## Plain English",
        "",
        *[f"- {line}" for line in report.explanation],
        "",
        "## Step Comparison",
        "",
        f"| Step | Compact | {_context_label(summary.baseline_context_mode)} | Expected Next | Compact Predicted | Baseline Predicted |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    baseline_by_step = {step.step: step for step in report.baseline.steps}
    for compact_step in report.compact.steps:
        baseline_step = baseline_by_step.get(compact_step.step)
        lines.append(
            "| "
            + " | ".join(
                [
                    str(compact_step.step),
                    "pass" if compact_step.passed else "fail",
                    "pass" if baseline_step and baseline_step.passed else "fail",
                    _format_action(compact_step.expected_next_action),
                    _format_action(compact_step.predicted_next_action),
                    _format_action(baseline_step.predicted_next_action)
                    if baseline_step
                    else "missing",
                ]
            )
            + " |"
        )
    (run_path / "eval_summary.md").write_text("\n".join(lines) + "\n")


def _format_action(action: BrowserAction) -> str:
    if action.type == "type":
        return f"type {action.target or ''}".strip()
    if action.type == "click":
        return f"click {action.target or ''}".strip()
    if action.type == "press":
        return f"press {action.key or ''}".strip()
    if action.type == "goto":
        return f"goto {action.url or ''}".strip()
    return action.type


def _token_reduction_pct(baseline_tokens: int, compact_tokens: int) -> float:
    if baseline_tokens <= 0:
        return 0.0
    return round(max(0.0, (baseline_tokens - compact_tokens) / baseline_tokens * 100), 2)


def _context_label(context_mode: ReplayContextMode) -> str:
    if context_mode == "vision_full_state":
        return "Vision full state"
    if context_mode == "full_state":
        return "Full state"
    return "Compact"


def _baseline_route_reason(context_mode: ReplayContextMode) -> str:
    if context_mode == "vision_full_state":
        return "Vision baseline uses uncompressed captured page state plus the full screenshot as model image input."
    return "Baseline uses the uncompressed captured page state and screenshot pointer."


def _resolve_target_alias(action: BrowserAction, observation: CompactObservation) -> BrowserAction:
    if not action.target:
        return action
    for item in observation.interactive:
        if _target_ref_matches(action.target, item):
            label = _target_label(item)
            if label and label != action.target:
                return action.model_copy(update={"target": label})
    return action


def _target_ref_matches(target: str, item: InteractiveElement) -> bool:
    aliases = {
        item.ref,
        item.name,
        str((item.attributes or {}).get("id") or ""),
        str((item.attributes or {}).get("name") or ""),
        str((item.attributes or {}).get("aria-label") or ""),
    }
    target_normalized = _normalize(target)
    return any(target_normalized == _normalize(alias) for alias in aliases if alias)


def _target_label(item: InteractiveElement) -> str:
    attrs = item.attributes or {}
    return (
        item.name
        or str(attrs.get("aria-label") or "")
        or str(attrs.get("name") or "")
        or str(attrs.get("id") or "")
        or item.ref
    )


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.strip().lower().split())


def _read_manifest_if_present(run_path: Path) -> RunManifest | None:
    manifest_path = run_path / "run.json"
    if not manifest_path.exists():
        return None
    return read_manifest(run_path)


def _goal_from_manifest(manifest: RunManifest | None) -> str:
    if manifest is None:
        return ""
    goal = manifest.metadata.get("goal")
    return str(goal) if goal else ""


def _accuracy(results: list[ReplayStepResult]) -> float:
    if not results:
        return 0.0
    return round(sum(1 for result in results if result.passed) / len(results), 3)


def _avg_reduction(results: list[ReplayStepResult]) -> float:
    if not results:
        return 0.0
    return round(sum(result.reduction_pct for result in results) / len(results), 2)
