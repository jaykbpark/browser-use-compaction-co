"""Arize AX observability helpers for BrowserDelta eval traces."""

from __future__ import annotations

import os
from typing import Any

_ARIZE_OTLP_ENDPOINT = "https://otlp.arize.com/v1"


def configure_arize_tracing(project_name: str) -> Any:
    """Set up OTel tracing that exports spans to Arize via OTLP/HTTP.

    Returns the configured ``TracerProvider`` so callers can flush on exit,
    or ``None`` when the required packages are missing.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        raise RuntimeError(
            "Install the [observability] extra to enable Arize tracing: "
            "pip install -e '.[observability]'"
        ) from exc

    api_key = os.environ.get("ARIZE_API_KEY", "")
    space_id = os.environ.get("ARIZE_SPACE_ID", "")
    if not api_key or not space_id:
        raise RuntimeError("ARIZE_API_KEY and ARIZE_SPACE_ID must be set for --arize tracing.")

    resource = Resource.create({"model_id": project_name, "model_version": "1.0"})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=f"{_ARIZE_OTLP_ENDPOINT}/traces",
        headers={
            "authorization": f"Bearer {api_key}",
            "space_id": space_id,
        },
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider


def trace_eval_step(
    tracer: Any,
    run_id: str,
    step: int,
    context_mode: str,
    observation_summary: str,
    expected_action: dict[str, Any],
    predicted_action: dict[str, Any],
    passed: bool,
    tokens_estimate: int,
    baseline_tokens_estimate: int,
    reduction_pct: float,
    route: str,
    rationale: str = "",
) -> None:
    """Emit a single OTel span for one eval step."""
    with tracer.start_as_current_span(f"eval_step_{run_id}_s{step}") as span:
        span.set_attribute("browserdelta.run_id", run_id)
        span.set_attribute("browserdelta.step", step)
        span.set_attribute("browserdelta.context_mode", context_mode)
        span.set_attribute("browserdelta.observation_summary", observation_summary)
        span.set_attribute("browserdelta.expected_action", str(expected_action))
        span.set_attribute("browserdelta.predicted_action", str(predicted_action))
        span.set_attribute("browserdelta.passed", passed)
        span.set_attribute("browserdelta.tokens_estimate", tokens_estimate)
        span.set_attribute("browserdelta.baseline_tokens_estimate", baseline_tokens_estimate)
        span.set_attribute("browserdelta.reduction_pct", reduction_pct)
        span.set_attribute("browserdelta.route", route)
        span.set_attribute("browserdelta.rationale", rationale)

        try:
            from opentelemetry.trace import StatusCode

            span.set_status(StatusCode.OK if passed else StatusCode.ERROR)
        except ImportError:
            pass


def trace_eval_suite(
    tracer: Any,
    suite: dict[str, Any],
) -> None:
    """Emit a parent span summarising the full eval suite run."""
    mode = suite.get("mode", "compact")
    predictor = suite.get("predictor", "unknown")
    summary = suite.get("summary", {})

    with tracer.start_as_current_span(f"eval_suite_{mode}_{predictor}") as span:
        span.set_attribute("browserdelta.suite_mode", mode)
        span.set_attribute("browserdelta.predictor", predictor)
        span.set_attribute("browserdelta.runs_count", summary.get("runs", 0))
        span.set_attribute("browserdelta.evaluated", summary.get("evaluated", 0))

        if mode == "comparison":
            span.set_attribute("browserdelta.compact_passed", summary.get("compact_passed", 0))
            span.set_attribute("browserdelta.baseline_passed", summary.get("baseline_passed", 0))
            span.set_attribute("browserdelta.compact_accuracy", summary.get("compact_accuracy", 0))
            span.set_attribute(
                "browserdelta.baseline_accuracy", summary.get("baseline_accuracy", 0)
            )
            span.set_attribute(
                "browserdelta.token_reduction_pct", summary.get("token_reduction_pct", 0)
            )
            span.set_attribute("browserdelta.compact_tokens", summary.get("compact_tokens", 0))
            span.set_attribute("browserdelta.baseline_tokens", summary.get("baseline_tokens", 0))
        else:
            span.set_attribute("browserdelta.passed", summary.get("passed", 0))
            span.set_attribute("browserdelta.accuracy", summary.get("accuracy", 0))
            span.set_attribute(
                "browserdelta.avg_reduction_pct", summary.get("avg_reduction_pct", 0)
            )
            span.set_attribute("browserdelta.compact_tokens", summary.get("compact_tokens", 0))
            span.set_attribute("browserdelta.baseline_tokens", summary.get("baseline_tokens", 0))

        for row in suite.get("runs", []):
            _trace_run_row(tracer, row)


def _trace_run_row(tracer: Any, row: dict[str, Any]) -> None:
    """Emit a child span for each evaluated run in the suite."""
    run_id = row.get("run_id", "unknown")
    with tracer.start_as_current_span(f"eval_run_{run_id}") as span:
        for key, value in row.items():
            if isinstance(value, (str, int, float, bool)):
                span.set_attribute(f"browserdelta.{key}", value)
