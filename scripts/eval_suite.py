#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from browserdelta.eval.runner import evaluate_comparison, evaluate_run  # noqa: E402
from browserdelta.schemas import EvalComparisonReport, ReplayReport  # noqa: E402


class EvalTarget(NamedTuple):
    run_path: Path
    goal: str | None = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay-evaluate multiple BrowserDelta runs and summarize benchmark metrics."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Run directories, task JSON files, or suite JSON files with a runs list.",
    )
    parser.add_argument("--predictor", default="heuristic", choices=["heuristic", "llm"])
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare compact replay against a baseline for each run.",
    )
    parser.add_argument(
        "--baseline-context",
        default="vision_full_state",
        choices=["full_state", "vision_full_state"],
        help="Baseline context mode to use with --compare.",
    )
    parser.add_argument("--json", action="store_true", help="Print the suite summary as JSON.")
    parser.add_argument(
        "--arize",
        action="store_true",
        help="Send eval traces to Arize via OTLP. Requires ARIZE_API_KEY and ARIZE_SPACE_ID.",
    )
    parser.add_argument(
        "--arize-project",
        default="browserdelta-hackathon",
        help="Arize project name (default: browserdelta-hackathon).",
    )
    args = parser.parse_args(argv)

    tracer_provider = None
    if args.arize:
        from browserdelta.observability import configure_arize_tracing

        tracer_provider = configure_arize_tracing(args.arize_project)

    suite = evaluate_suite(
        args.inputs,
        predictor=args.predictor,
        compare=args.compare,
        baseline_context_mode=args.baseline_context,  # type: ignore[arg-type]
    )

    if args.arize and tracer_provider is not None:
        from opentelemetry import trace

        from browserdelta.observability import trace_eval_suite

        tracer = trace.get_tracer("browserdelta.eval")
        trace_eval_suite(tracer, suite)
        tracer_provider.force_flush(timeout_millis=15000)

    if args.json:
        print(json.dumps(suite, indent=2))
    else:
        print(format_table(suite))
    return 0


def evaluate_suite(
    inputs: list[Path],
    predictor: str = "heuristic",
    root: Path | None = None,
    compare: bool = False,
    baseline_context_mode: str = "vision_full_state",
) -> dict[str, Any]:
    root = root or ROOT
    targets = expand_targets(inputs, root=root)
    if compare:
        rows = [
            summarize_comparison(
                evaluate_comparison(
                    target.run_path,
                    goal=target.goal,
                    predictor=predictor,
                    baseline_context_mode=baseline_context_mode,  # type: ignore[arg-type]
                )
            )
            for target in targets
        ]
        return {
            "predictor": predictor,
            "mode": "comparison",
            "baseline_context_mode": baseline_context_mode,
            "runs": rows,
            "summary": summarize_comparison_rows(rows),
        }

    rows = [
        summarize_report(evaluate_run(target.run_path, goal=target.goal, predictor=predictor))
        for target in targets
    ]
    return {
        "predictor": predictor,
        "mode": "compact",
        "runs": rows,
        "summary": summarize_rows(rows),
    }


def expand_targets(inputs: list[Path], root: Path | None = None) -> list[EvalTarget]:
    root = root or ROOT
    targets: list[EvalTarget] = []
    for input_path in inputs:
        path = _resolve_cli_path(input_path)
        if path.is_dir():
            targets.append(EvalTarget(path))
            continue
        if path.is_file():
            targets.extend(_targets_from_json(path, root=root))
            continue
        raise FileNotFoundError(f"Evaluation input does not exist: {input_path}")
    return targets


def summarize_report(report: ReplayReport) -> dict[str, Any]:
    return {
        "run_id": report.run_id,
        "predictor": report.predictor,
        "passed": report.passed_steps,
        "evaluated": report.evaluated_steps,
        "passed_evaluated": f"{report.passed_steps}/{report.evaluated_steps}",
        "accuracy": report.next_action_accuracy,
        "avg_reduction_pct": report.avg_reduction_pct,
        "compact_tokens": report.compact_tokens,
        "baseline_tokens": report.baseline_tokens,
    }


def summarize_comparison(report: EvalComparisonReport) -> dict[str, Any]:
    summary = report.summary
    return {
        "run_id": report.run_id,
        "predictor": report.predictor,
        "baseline_context_mode": summary.baseline_context_mode,
        "compact_passed": summary.compact_passed_steps,
        "baseline_passed": summary.baseline_passed_steps,
        "evaluated": summary.evaluated_steps,
        "compact_passed_evaluated": (f"{summary.compact_passed_steps}/{summary.evaluated_steps}"),
        "baseline_passed_evaluated": (f"{summary.baseline_passed_steps}/{summary.evaluated_steps}"),
        "compact_accuracy": summary.compact_accuracy,
        "baseline_accuracy": summary.baseline_accuracy,
        "accuracy_delta": summary.accuracy_delta,
        "token_reduction_pct": summary.token_reduction_pct,
        "token_savings": summary.token_savings,
        "compact_tokens": summary.compact_tokens,
        "baseline_tokens": summary.baseline_tokens,
        "verdict": report.verdict,
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = sum(int(row["evaluated"]) for row in rows)
    passed = sum(int(row["passed"]) for row in rows)
    compact_tokens = sum(int(row["compact_tokens"]) for row in rows)
    baseline_tokens = sum(int(row["baseline_tokens"]) for row in rows)
    weighted_reduction = sum(
        float(row["avg_reduction_pct"]) * int(row["evaluated"]) for row in rows
    )

    return {
        "runs": len(rows),
        "passed": passed,
        "evaluated": evaluated,
        "passed_evaluated": f"{passed}/{evaluated}",
        "accuracy": round(passed / evaluated, 3) if evaluated else 0.0,
        "avg_reduction_pct": round(weighted_reduction / evaluated, 2) if evaluated else 0.0,
        "compact_tokens": compact_tokens,
        "baseline_tokens": baseline_tokens,
    }


def summarize_comparison_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = sum(int(row["evaluated"]) for row in rows)
    compact_passed = sum(int(row["compact_passed"]) for row in rows)
    baseline_passed = sum(int(row["baseline_passed"]) for row in rows)
    compact_tokens = sum(int(row["compact_tokens"]) for row in rows)
    baseline_tokens = sum(int(row["baseline_tokens"]) for row in rows)
    token_savings = max(0, baseline_tokens - compact_tokens)
    compact_accuracy = round(compact_passed / evaluated, 3) if evaluated else 0.0
    baseline_accuracy = round(baseline_passed / evaluated, 3) if evaluated else 0.0

    return {
        "runs": len(rows),
        "baseline_context_mode": _common_value(rows, "baseline_context_mode") or "mixed",
        "compact_passed": compact_passed,
        "baseline_passed": baseline_passed,
        "evaluated": evaluated,
        "compact_passed_evaluated": f"{compact_passed}/{evaluated}",
        "baseline_passed_evaluated": f"{baseline_passed}/{evaluated}",
        "compact_accuracy": compact_accuracy,
        "baseline_accuracy": baseline_accuracy,
        "accuracy_delta": round(compact_accuracy - baseline_accuracy, 3),
        "token_reduction_pct": (
            round(max(0.0, token_savings / baseline_tokens * 100), 2) if baseline_tokens else 0.0
        ),
        "token_savings": token_savings,
        "compact_tokens": compact_tokens,
        "baseline_tokens": baseline_tokens,
    }


def format_table(suite: dict[str, Any]) -> str:
    rows = list(suite["runs"])
    summary = dict(suite["summary"])
    if suite.get("mode") == "comparison":
        return format_comparison_table(suite)

    table_rows = [_display_row(row) for row in rows]
    table_rows.append(
        {
            "run_id": "TOTAL",
            "predictor": str(suite["predictor"]),
            "passed/evaluated": summary["passed_evaluated"],
            "accuracy": _format_accuracy(float(summary["accuracy"])),
            "avg_reduction_pct": _format_pct(float(summary["avg_reduction_pct"])),
            "compact_tokens": str(summary["compact_tokens"]),
            "baseline_tokens": str(summary["baseline_tokens"]),
        }
    )

    columns = [
        "run_id",
        "predictor",
        "passed/evaluated",
        "accuracy",
        "avg_reduction_pct",
        "compact_tokens",
        "baseline_tokens",
    ]
    widths = {
        column: max(len(column), *(len(row[column]) for row in table_rows)) for column in columns
    }

    header = "  ".join(column.ljust(widths[column]) for column in columns)
    separator = "  ".join("-" * widths[column] for column in columns)
    body = [
        "  ".join(row[column].ljust(widths[column]) for column in columns) for row in table_rows
    ]
    return "\n".join([header, separator, *body])


def format_comparison_table(suite: dict[str, Any]) -> str:
    rows = list(suite["runs"])
    summary = dict(suite["summary"])
    table_rows = [_display_comparison_row(row) for row in rows]
    table_rows.append(
        {
            "run_id": "TOTAL",
            "predictor": str(suite["predictor"]),
            "compact": summary["compact_passed_evaluated"],
            "baseline": summary["baseline_passed_evaluated"],
            "baseline_context": str(summary["baseline_context_mode"]),
            "saved": _format_pct(float(summary["token_reduction_pct"])),
            "compact_tokens": str(summary["compact_tokens"]),
            "baseline_tokens": str(summary["baseline_tokens"]),
            "verdict": _summary_verdict(summary),
        }
    )

    columns = [
        "run_id",
        "predictor",
        "compact",
        "baseline",
        "baseline_context",
        "saved",
        "compact_tokens",
        "baseline_tokens",
        "verdict",
    ]
    widths = {
        column: max(len(column), *(len(row[column]) for row in table_rows)) for column in columns
    }
    header = "  ".join(column.ljust(widths[column]) for column in columns)
    separator = "  ".join("-" * widths[column] for column in columns)
    body = [
        "  ".join(row[column].ljust(widths[column]) for column in columns) for row in table_rows
    ]
    return "\n".join([header, separator, *body])


def _display_row(row: dict[str, Any]) -> dict[str, str]:
    return {
        "run_id": str(row["run_id"]),
        "predictor": str(row["predictor"]),
        "passed/evaluated": str(row["passed_evaluated"]),
        "accuracy": _format_accuracy(float(row["accuracy"])),
        "avg_reduction_pct": _format_pct(float(row["avg_reduction_pct"])),
        "compact_tokens": str(row["compact_tokens"]),
        "baseline_tokens": str(row["baseline_tokens"]),
    }


def _display_comparison_row(row: dict[str, Any]) -> dict[str, str]:
    return {
        "run_id": str(row["run_id"]),
        "predictor": str(row["predictor"]),
        "compact": str(row["compact_passed_evaluated"]),
        "baseline": str(row["baseline_passed_evaluated"]),
        "baseline_context": str(row["baseline_context_mode"]),
        "saved": _format_pct(float(row["token_reduction_pct"])),
        "compact_tokens": str(row["compact_tokens"]),
        "baseline_tokens": str(row["baseline_tokens"]),
        "verdict": str(row["verdict"]),
    }


def _summary_verdict(summary: dict[str, Any]) -> str:
    if summary["compact_accuracy"] >= summary["baseline_accuracy"]:
        return "compact_matches_or_beats_baseline"
    return "compact_loses_accuracy"


def _format_accuracy(value: float) -> str:
    return f"{value * 100:.1f}%"


def _format_pct(value: float) -> str:
    return f"{value:.2f}%"


def _common_value(rows: list[dict[str, Any]], key: str) -> str | None:
    values = {str(row.get(key, "")) for row in rows}
    return values.pop() if len(values) == 1 else None


def _targets_from_json(path: Path, root: Path) -> list[EvalTarget]:
    payload = json.loads(path.read_text())
    return _targets_from_payload(payload, base_dir=path.parent, root=root)


def _targets_from_payload(payload: Any, base_dir: Path, root: Path) -> list[EvalTarget]:
    if isinstance(payload, list):
        return _targets_from_entries(payload, base_dir=base_dir, root=root)

    if not isinstance(payload, dict):
        raise ValueError("Evaluation JSON must be an object or list.")

    if "runs" in payload:
        return _targets_from_entries(payload["runs"], base_dir=base_dir, root=root)
    if "run_paths" in payload:
        return _targets_from_entries(payload["run_paths"], base_dir=base_dir, root=root)
    if "tasks" in payload:
        return _targets_from_task_entries(payload["tasks"], base_dir=base_dir, root=root)
    if "start_url" in payload and "actions" in payload:
        return [_target_from_task(payload, root=root)]

    return [_target_from_entry(payload, base_dir=base_dir, root=root)]


def _targets_from_entries(entries: Any, base_dir: Path, root: Path) -> list[EvalTarget]:
    if not isinstance(entries, list):
        raise ValueError("Suite runs must be a list.")
    return [_target_from_entry(entry, base_dir=base_dir, root=root) for entry in entries]


def _targets_from_task_entries(entries: Any, base_dir: Path, root: Path) -> list[EvalTarget]:
    if not isinstance(entries, list):
        raise ValueError("Suite tasks must be a list.")

    targets: list[EvalTarget] = []
    for entry in entries:
        task_path = _path_from_entry(entry, base_dir=base_dir, root=root)
        targets.extend(_targets_from_json(task_path, root=root))
    return targets


def _target_from_entry(entry: Any, base_dir: Path, root: Path) -> EvalTarget:
    if isinstance(entry, str):
        return EvalTarget(_resolve_manifest_path(entry, base_dir=base_dir, root=root))

    if not isinstance(entry, dict):
        raise ValueError("Suite entries must be strings or objects.")

    if "task" in entry or "task_path" in entry:
        key = "task" if "task" in entry else "task_path"
        task_path = _resolve_manifest_path(str(entry[key]), base_dir=base_dir, root=root)
        targets = _targets_from_json(task_path, root=root)
        if len(targets) != 1:
            raise ValueError(f"Task entry {task_path} expanded to {len(targets)} targets.")
        target = targets[0]
        return EvalTarget(target.run_path, goal=str(entry.get("goal") or target.goal or ""))

    for key in ("path", "run_path", "run_dir"):
        if key in entry:
            run_path = _resolve_manifest_path(str(entry[key]), base_dir=base_dir, root=root)
            goal = entry.get("goal")
            return EvalTarget(run_path, goal=str(goal) if goal is not None else None)

    run_id = entry.get("run_id") or entry.get("id")
    if run_id:
        goal = entry.get("goal")
        return EvalTarget(
            root / "runs" / str(run_id),
            goal=str(goal) if goal is not None else None,
        )

    raise ValueError("Suite entry must include path, run_path, run_dir, run_id, id, or task.")


def _target_from_task(task: dict[str, Any], root: Path) -> EvalTarget:
    run_id = task.get("run_id") or task.get("id")
    if not run_id:
        raise ValueError("Task JSON must include id or run_id to resolve a run folder.")
    goal = task.get("goal")
    return EvalTarget(
        root / "runs" / str(run_id),
        goal=str(goal) if goal is not None else None,
    )


def _path_from_entry(entry: Any, base_dir: Path, root: Path) -> Path:
    if isinstance(entry, str):
        return _resolve_manifest_path(entry, base_dir=base_dir, root=root)
    if isinstance(entry, dict):
        for key in ("task", "task_path", "path"):
            if key in entry:
                return _resolve_manifest_path(str(entry[key]), base_dir=base_dir, root=root)
    raise ValueError("Task entries must be paths or objects with task/task_path/path.")


def _resolve_cli_path(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def _resolve_manifest_path(value: str, base_dir: Path, root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path

    base_candidate = base_dir / path
    if base_candidate.exists():
        return base_candidate

    root_candidate = root / path
    if root_candidate.exists():
        return root_candidate

    return base_candidate


if __name__ == "__main__":
    raise SystemExit(main())
