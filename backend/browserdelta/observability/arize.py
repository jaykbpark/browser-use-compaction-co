from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from browserdelta.config import get_settings
from browserdelta.schemas import (
    BrowserAction,
    CompactObservation,
    EvalComparisonReport,
    ReplayReport,
    ReplayStepResult,
)


_TRACER_NAME = "browserdelta.eval"


@dataclass
class ArizeEvalTracer:
    enabled: bool = False
    reason: str = ""
    tracer: Any | None = None
    provider: Any | None = None
    project_name: str = "browserdelta-hackathon"

    @contextmanager
    def comparison_span(
        self,
        *,
        run_path: Path,
        predictor: str,
        baseline_context_mode: str,
        goal: str,
    ) -> Iterator[Any | None]:
        if not self.enabled or self.tracer is None:
            yield None
            return

        with self.tracer.start_as_current_span("browserdelta.eval.comparison") as span:
            _set_common_span_attributes(span, "CHAIN")
            span.set_attribute("browserdelta.run_path", str(run_path))
            span.set_attribute("browserdelta.predictor", predictor)
            span.set_attribute("browserdelta.baseline_context_mode", baseline_context_mode)
            span.set_attribute("input.value", goal or str(run_path))
            yield span

    @contextmanager
    def run_span(
        self,
        *,
        run_id: str,
        run_path: Path,
        predictor: str,
        context_mode: str,
        goal: str,
    ) -> Iterator[Any | None]:
        if not self.enabled or self.tracer is None:
            yield None
            return

        with self.tracer.start_as_current_span("browserdelta.eval.run") as span:
            _set_common_span_attributes(span, "CHAIN")
            span.set_attribute("browserdelta.run_id", run_id)
            span.set_attribute("browserdelta.run_path", str(run_path))
            span.set_attribute("browserdelta.predictor", predictor)
            span.set_attribute("browserdelta.context_mode", context_mode)
            span.set_attribute("input.value", goal or run_id)
            yield span

    @contextmanager
    def step_span(
        self,
        *,
        run_id: str,
        context_mode: str,
        step: int,
        observation: CompactObservation,
        expected_next_action: BrowserAction,
        previous_action: BrowserAction,
    ) -> Iterator[Any | None]:
        if not self.enabled or self.tracer is None:
            yield None
            return

        with self.tracer.start_as_current_span("browserdelta.eval.step") as span:
            _set_common_span_attributes(span, "EVALUATOR")
            span.set_attribute("browserdelta.run_id", run_id)
            span.set_attribute("browserdelta.context_mode", context_mode)
            span.set_attribute("browserdelta.step", step)
            span.set_attribute("browserdelta.route", observation.route)
            span.set_attribute("browserdelta.fallback", observation.fallback)
            span.set_attribute("browserdelta.visual_changed_pct", observation.visual_changed_pct)
            span.set_attribute(
                "browserdelta.visual_raw_changed_pct",
                observation.visual_raw_changed_pct,
            )
            if observation.visual_ssim_score is not None:
                span.set_attribute(
                    "browserdelta.visual_ssim_score",
                    observation.visual_ssim_score,
                )
            if observation.visual_phash_distance is not None:
                span.set_attribute(
                    "browserdelta.visual_phash_distance",
                    observation.visual_phash_distance,
                )
            span.set_attribute("browserdelta.crop_count", len(observation.crop_paths))
            span.set_attribute("browserdelta.expected_action.type", expected_next_action.type)
            span.set_attribute(
                "browserdelta.expected_action.target",
                expected_next_action.target or "",
            )
            span.set_attribute(
                "input.value",
                _json_dumps(
                    {
                        "previous_action": _action_dict(previous_action),
                        "expected_next_action": _action_dict(expected_next_action),
                        "observation_summary": observation.summary,
                        "route": observation.route,
                        "fallback": observation.fallback,
                    }
                ),
            )
            yield span

    @contextmanager
    def live_suite_span(
        self,
        *,
        suite: str,
        policy: str,
        modes: list[str],
    ) -> Iterator[Any | None]:
        if not self.enabled or self.tracer is None:
            yield None
            return

        with self.tracer.start_as_current_span("browserdelta.browsergym_live.suite") as span:
            _set_common_span_attributes(span, "CHAIN")
            span.set_attribute("browserdelta.suite", suite)
            span.set_attribute("browserdelta.policy", policy)
            span.set_attribute("browserdelta.modes", ",".join(modes))
            span.set_attribute("input.value", _json_dumps({"suite": suite, "modes": modes}))
            yield span

    @contextmanager
    def live_episode_span(
        self,
        *,
        env_id: str,
        run_id: str,
        mode: str,
        policy: str,
        goal: str,
    ) -> Iterator[Any | None]:
        if not self.enabled or self.tracer is None:
            yield None
            return

        with self.tracer.start_as_current_span("browserdelta.browsergym_live.episode") as span:
            _set_common_span_attributes(span, "CHAIN")
            span.set_attribute("browserdelta.env_id", env_id)
            span.set_attribute("browserdelta.run_id", run_id)
            span.set_attribute("browserdelta.context_mode", mode)
            span.set_attribute("browserdelta.policy", policy)
            span.set_attribute("input.value", goal or env_id)
            yield span

    @contextmanager
    def live_step_span(
        self,
        *,
        env_id: str,
        run_id: str,
        mode: str,
        step: int,
        observation: CompactObservation,
    ) -> Iterator[Any | None]:
        if not self.enabled or self.tracer is None:
            yield None
            return

        with self.tracer.start_as_current_span("browserdelta.browsergym_live.step") as span:
            _set_common_span_attributes(span, "AGENT")
            span.set_attribute("browserdelta.env_id", env_id)
            span.set_attribute("browserdelta.run_id", run_id)
            span.set_attribute("browserdelta.context_mode", mode)
            span.set_attribute("browserdelta.step", step)
            span.set_attribute("browserdelta.route", observation.route)
            span.set_attribute("browserdelta.fallback", observation.fallback)
            span.set_attribute("browserdelta.compact_tokens", observation.tokens_estimate)
            span.set_attribute(
                "browserdelta.baseline_tokens",
                observation.baseline_tokens_estimate,
            )
            span.set_attribute(
                "input.value",
                _json_dumps(
                    {
                        "summary": observation.summary,
                        "llm_observation": observation.llm_observation,
                        "route": observation.route,
                        "fallback": observation.fallback,
                    }
                ),
            )
            yield span

    def record_step(self, span: Any | None, result: ReplayStepResult) -> None:
        if span is None:
            return
        span.set_attribute("browserdelta.passed", result.passed)
        span.set_attribute("browserdelta.match_reason", result.match_reason)
        span.set_attribute("browserdelta.confidence", result.confidence)
        span.set_attribute("browserdelta.compact_tokens", result.tokens_estimate)
        span.set_attribute("browserdelta.baseline_tokens", result.baseline_tokens_estimate)
        span.set_attribute("browserdelta.reduction_pct", result.reduction_pct)
        span.set_attribute("browserdelta.predicted_action.type", result.predicted_next_action.type)
        span.set_attribute(
            "browserdelta.predicted_action.target",
            result.predicted_next_action.target or "",
        )
        span.set_attribute(
            "output.value",
            _json_dumps(
                {
                    "passed": result.passed,
                    "match_reason": result.match_reason,
                    "predicted_next_action": _action_dict(result.predicted_next_action),
                    "compact_tokens": result.tokens_estimate,
                    "baseline_tokens": result.baseline_tokens_estimate,
                    "reduction_pct": result.reduction_pct,
                }
            ),
        )
        _set_status(span, result.passed, result.match_reason)

    def record_report(self, span: Any | None, report: ReplayReport) -> None:
        if span is None:
            return
        span.set_attribute("browserdelta.evaluated_steps", report.evaluated_steps)
        span.set_attribute("browserdelta.passed_steps", report.passed_steps)
        span.set_attribute("browserdelta.next_action_accuracy", report.next_action_accuracy)
        span.set_attribute("browserdelta.compact_tokens", report.compact_tokens)
        span.set_attribute("browserdelta.baseline_tokens", report.baseline_tokens)
        span.set_attribute("browserdelta.avg_reduction_pct", report.avg_reduction_pct)
        span.set_attribute(
            "output.value",
            _json_dumps(
                {
                    "run_id": report.run_id,
                    "context_mode": report.context_mode,
                    "passed_steps": report.passed_steps,
                    "evaluated_steps": report.evaluated_steps,
                    "next_action_accuracy": report.next_action_accuracy,
                    "compact_tokens": report.compact_tokens,
                    "baseline_tokens": report.baseline_tokens,
                    "avg_reduction_pct": report.avg_reduction_pct,
                }
            ),
        )
        _set_status(span, report.passed_steps == report.evaluated_steps, "run evaluation complete")

    def record_comparison(self, span: Any | None, report: EvalComparisonReport) -> None:
        if span is None:
            return
        summary = report.summary
        span.set_attribute("browserdelta.verdict", report.verdict)
        span.set_attribute("browserdelta.compact_accuracy", summary.compact_accuracy)
        span.set_attribute("browserdelta.baseline_accuracy", summary.baseline_accuracy)
        span.set_attribute("browserdelta.accuracy_delta", summary.accuracy_delta)
        span.set_attribute("browserdelta.token_reduction_pct", summary.token_reduction_pct)
        span.set_attribute("browserdelta.token_savings", summary.token_savings)
        span.set_attribute(
            "output.value",
            _json_dumps(
                {
                    "verdict": report.verdict,
                    "compact_accuracy": summary.compact_accuracy,
                    "baseline_accuracy": summary.baseline_accuracy,
                    "accuracy_delta": summary.accuracy_delta,
                    "token_reduction_pct": summary.token_reduction_pct,
                    "token_savings": summary.token_savings,
                }
            ),
        )
        _set_status(span, report.verdict != "compact_loses_accuracy", report.verdict)

    def record_live_step(self, span: Any | None, decision: dict[str, Any]) -> None:
        if span is None:
            return
        span.set_attribute("browserdelta.compact_tokens", int(decision["tokens_estimate"]))
        span.set_attribute(
            "browserdelta.baseline_tokens",
            int(decision["baseline_tokens_estimate"]),
        )
        raw_action = _dict_action(decision.get("raw_action"))
        resolved_action = _dict_action(decision.get("resolved_action"))
        span.set_attribute("browserdelta.raw_action.type", str(raw_action.get("type") or ""))
        span.set_attribute("browserdelta.raw_action.target", str(raw_action.get("target") or ""))
        span.set_attribute(
            "browserdelta.resolved_action.type",
            str(resolved_action.get("type") or ""),
        )
        span.set_attribute(
            "browserdelta.resolved_action.target",
            str(resolved_action.get("target") or ""),
        )
        span.set_attribute("browserdelta.browsergym_action", decision.get("browsergym_action", ""))
        span.set_attribute(
            "output.value",
            _json_dumps(
                {
                    "raw_action": raw_action,
                    "resolved_action": resolved_action,
                    "browsergym_action": decision.get("browsergym_action"),
                    "tokens_estimate": decision.get("tokens_estimate"),
                    "baseline_tokens_estimate": decision.get("baseline_tokens_estimate"),
                }
            ),
        )
        _set_status(span, True, "live step complete")

    def record_live_episode(self, span: Any | None, result: dict[str, Any]) -> None:
        if span is None:
            return
        span.set_attribute("browserdelta.success", bool(result.get("success")))
        span.set_attribute("browserdelta.reward", float(result.get("reward") or 0.0))
        span.set_attribute("browserdelta.steps", int(result.get("steps") or 0))
        span.set_attribute("browserdelta.compact_tokens", int(result.get("decision_tokens") or 0))
        span.set_attribute("browserdelta.baseline_tokens", int(result.get("baseline_tokens") or 0))
        span.set_attribute(
            "browserdelta.token_reduction_pct",
            float(result.get("token_reduction_pct") or 0.0),
        )
        span.set_attribute("browserdelta.error", str(result.get("error") or ""))
        span.set_attribute(
            "output.value",
            _json_dumps(
                {
                    "env_id": result.get("env_id"),
                    "run_id": result.get("run_id"),
                    "mode": result.get("mode"),
                    "success": result.get("success"),
                    "reward": result.get("reward"),
                    "steps": result.get("steps"),
                    "decision_tokens": result.get("decision_tokens"),
                    "baseline_tokens": result.get("baseline_tokens"),
                    "token_reduction_pct": result.get("token_reduction_pct"),
                    "error": result.get("error"),
                }
            ),
        )
        _set_status(span, bool(result.get("success")) and not result.get("error"), "live episode")

    def record_live_suite(self, span: Any | None, report: dict[str, Any]) -> None:
        if span is None:
            return
        summary = report.get("summary") or {}
        span.set_attribute("browserdelta.episodes", int(summary.get("episodes") or 0))
        span.set_attribute(
            "browserdelta.failure_classes",
            _json_dumps(dict(summary.get("failure_classes") or {})),
        )
        span.set_attribute("output.value", _json_dumps(summary))
        _set_status(span, True, "live suite complete")

    def flush(self) -> None:
        if self.provider is None:
            return
        force_flush = getattr(self.provider, "force_flush", None)
        if callable(force_flush):
            force_flush()

    def shutdown(self) -> None:
        if self.provider is None:
            return
        self.flush()
        shutdown = getattr(self.provider, "shutdown", None)
        if callable(shutdown):
            shutdown()


def start_arize_tracing(enabled: bool, project_name: str | None = None) -> ArizeEvalTracer:
    if not enabled:
        return ArizeEvalTracer(enabled=False)

    settings = get_settings()
    arize_project = project_name or settings.arize_project_name or "browserdelta-hackathon"
    if not settings.arize_api_key or not settings.arize_space_id:
        return ArizeEvalTracer(
            enabled=False,
            reason="ARIZE_API_KEY and ARIZE_SPACE_ID are required for --arize.",
            project_name=arize_project,
        )

    try:
        from arize.otel import register
        from opentelemetry import trace
    except ImportError:
        return ArizeEvalTracer(
            enabled=False,
            reason=(
                "Arize tracing dependencies are missing. Install with "
                'pip install -e ".[observability]"'
            ),
            project_name=arize_project,
        )

    provider = register(
        space_id=settings.arize_space_id,
        api_key=settings.arize_api_key,
        project_name=arize_project,
        verbose=False,
    )
    tracer = trace.get_tracer(_TRACER_NAME)
    return ArizeEvalTracer(
        enabled=True,
        tracer=tracer,
        provider=provider,
        project_name=arize_project,
    )


def noop_arize_tracer() -> ArizeEvalTracer:
    return ArizeEvalTracer(enabled=False)


def _set_common_span_attributes(span: Any, span_kind: str) -> None:
    try:
        from openinference.semconv.trace import SpanAttributes

        span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, span_kind)
    except ImportError:
        span.set_attribute("openinference.span.kind", span_kind)


def _set_status(span: Any, ok: bool, description: str) -> None:
    try:
        from opentelemetry.trace import Status, StatusCode

        if ok:
            span.set_status(Status(StatusCode.OK))
        else:
            span.set_status(Status(StatusCode.ERROR, description))
    except ImportError:
        return


def _action_dict(action: BrowserAction) -> dict[str, Any]:
    return action.model_dump(mode="json", exclude_none=True)


def _dict_action(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)
