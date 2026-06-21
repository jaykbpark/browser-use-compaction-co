#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from browserdelta.eval.runner import evaluate_comparison, evaluate_run  # noqa: E402
from browserdelta.observability.arize import start_arize_tracing  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay-evaluate a compacted BrowserDelta run.")
    parser.add_argument("run_path", type=Path)
    parser.add_argument("--goal", help="Override the goal stored in run.json metadata.")
    parser.add_argument("--predictor", default="heuristic", choices=["heuristic", "llm"])
    parser.add_argument(
        "--context-mode",
        default="compact",
        choices=["compact", "full_state", "vision_full_state"],
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare compact replay against a baseline and write eval_summary.md.",
    )
    parser.add_argument(
        "--baseline-context",
        default="vision_full_state",
        choices=["full_state", "vision_full_state"],
        help="Baseline context mode to use with --compare.",
    )
    parser.add_argument("--arize", action="store_true", help="Emit Arize AX traces.")
    parser.add_argument("--arize-project", help="Override ARIZE_PROJECT_NAME for this run.")
    parser.add_argument("--json", action="store_true", help="Print the full report JSON.")
    args = parser.parse_args()
    tracer = start_arize_tracing(args.arize, project_name=args.arize_project)
    if args.arize and not tracer.enabled:
        print(f"Arize tracing disabled: {tracer.reason}", file=sys.stderr)

    if args.compare:
        try:
            comparison = evaluate_comparison(
                args.run_path,
                goal=args.goal,
                predictor=args.predictor,
                baseline_context_mode=args.baseline_context,  # type: ignore[arg-type]
                arize_tracer=tracer,
            )
        finally:
            tracer.flush()
        if args.json:
            print(json.dumps(comparison.model_dump(mode="json"), indent=2))
            return
        print(
            f"comparison eval: compact {comparison.summary.compact_passed_steps}/"
            f"{comparison.summary.evaluated_steps}, "
            f"{comparison.summary.baseline_context_mode} baseline "
            f"{comparison.summary.baseline_passed_steps}/{comparison.summary.evaluated_steps}"
        )
        print(
            f"tokens: {comparison.summary.compact_tokens} compact vs "
            f"{comparison.summary.baseline_tokens} "
            f"{comparison.summary.baseline_context_mode} baseline, "
            f"{comparison.summary.token_reduction_pct:.2f}% saved"
        )
        print(f"verdict: {comparison.verdict}")
        print(f"wrote {args.run_path / 'eval_comparison.json'}")
        print(f"wrote {args.run_path / 'eval_summary.md'}")
        return

    try:
        report = evaluate_run(
            args.run_path,
            goal=args.goal,
            predictor=args.predictor,
            context_mode=args.context_mode,  # type: ignore[arg-type]
            arize_tracer=tracer,
        )
    finally:
        tracer.flush()

    if args.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
        return

    print(
        f"replay eval: {report.passed_steps}/{report.evaluated_steps} "
        f"next actions matched ({report.next_action_accuracy * 100:.1f}%)"
    )
    print(
        f"tokens: {report.compact_tokens} compact vs {report.baseline_tokens} baseline, "
        f"{report.avg_reduction_pct:.2f}% avg saved"
    )
    for step in report.steps:
        status = "pass" if step.passed else "fail"
        expected = step.expected_next_action
        predicted = step.predicted_next_action
        print(
            f"step {step.step}: {status} - expected {expected.type} {expected.target or ''}; "
            f"predicted {predicted.type} {predicted.target or ''}"
        )
    report_name = (
        "eval_report.json"
        if report.context_mode == "compact"
        else f"eval_{report.context_mode}_report.json"
    )
    print(f"wrote {args.run_path / report_name}")


if __name__ == "__main__":
    main()
