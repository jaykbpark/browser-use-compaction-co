from __future__ import annotations

from typing import Any

try:
    from arize.experiments.evaluators.base import EvaluationResult, Evaluator
except ImportError:  # Arize hosted code-eval sandbox has used this path.
    from arize.experimental.datasets.experiments.evaluators.base import (  # type: ignore
        EvaluationResult,
        Evaluator,
    )


class BrowserDeltaActionPreservation(Evaluator):
    """Score whether BrowserDelta preserved the next action while saving tokens."""

    def evaluate(
        self,
        passed: Any = None,
        compact_tokens: Any = None,
        baseline_tokens: Any = None,
        reduction_pct: Any = None,
        route: Any = None,
        fallback: Any = None,
        match_reason: Any = None,
        **kwargs: Any,
    ) -> EvaluationResult:
        did_preserve = _as_bool(passed)
        compact = _as_float(compact_tokens)
        baseline = _as_float(baseline_tokens)
        reduction = _as_float(reduction_pct)

        if reduction is None and compact is not None and baseline and baseline > 0:
            reduction = max(0.0, (baseline - compact) / baseline * 100.0)

        route_text = _as_text(route) or "unknown_route"
        fallback_text = _as_text(fallback) or "unknown_fallback"
        reason_text = _as_text(match_reason) or "no match reason"

        if did_preserve is None or reduction is None:
            return EvaluationResult(
                label="missing_eval_data",
                score=0.0,
                explanation=(
                    "Required BrowserDelta eval fields were missing from the span. "
                    f"passed={passed!r}, reduction_pct={reduction_pct!r}."
                ),
            )

        if not did_preserve:
            return EvaluationResult(
                label="regressed_next_action",
                score=0.0,
                explanation=(
                    "Compact observation did not preserve the expected next action. "
                    f"route={route_text}, fallback={fallback_text}, reason={reason_text}."
                ),
            )

        if reduction >= 70.0:
            return EvaluationResult(
                label="preserved_high_compression",
                score=1.0,
                explanation=(
                    "Compact observation preserved the next action and saved "
                    f"{reduction:.1f}% tokens. route={route_text}, fallback={fallback_text}."
                ),
            )

        if reduction > 0.0:
            return EvaluationResult(
                label="preserved_low_compression",
                score=0.5,
                explanation=(
                    "Compact observation preserved the next action but token savings were modest: "
                    f"{reduction:.1f}%. route={route_text}, fallback={fallback_text}."
                ),
            )

        return EvaluationResult(
            label="preserved_no_compression",
            score=0.25,
            explanation=(
                "Compact observation preserved the next action but did not reduce token load. "
                f"route={route_text}, fallback={fallback_text}."
            ),
        )


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "pass", "passed"}:
        return True
    if text in {"false", "0", "no", "n", "fail", "failed"}:
        return False
    return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
