#!/usr/bin/env python3
"""Evaluate a single recorded run (baseline vs compact) with the heuristic predictor.

    python scripts/eval_run.py runs/search_filter

If a matching tasks/<run_name>.json exists it is used to score next-action
grounding; otherwise token/route/fallback metrics are still reported.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from browserdelta.eval.ab import evaluate_run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate one recorded run.")
    parser.add_argument("run_path", type=Path, help="Path to runs/<run_id>.")
    parser.add_argument(
        "--task", type=Path, default=None, help="Task JSON (default: tasks/<run_id>.json)."
    )
    parser.add_argument(
        "--predictor", default="heuristic", help="Next-action predictor (default: heuristic)."
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="Optional path to write the report JSON."
    )
    args = parser.parse_args()

    task_path = args.task or (ROOT / "tasks" / f"{args.run_path.name}.json")
    task = json.loads(task_path.read_text()) if task_path.exists() else None

    report = evaluate_run(args.run_path, task=task, predictor=args.predictor)

    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n")

    summary = report["summary"]
    tokens = summary["tokens"]
    print(f"run={args.run_path.name} steps={summary['n_steps']} predictor={args.predictor}")
    print(
        f"tokens baseline={tokens['baseline_total']} compact={tokens['compact_total']} "
        f"savings={tokens['savings_pct']}% ratio={tokens['compression_ratio']}x"
    )
    print(
        f"routes={summary['routes_compact']} fallback_rate={summary['fallback']['fallback_rate']}"
    )
    na = summary["next_action"]
    print(
        f"next-action baseline={na['baseline_accuracy']} compact={na['compact_accuracy']} "
        f"(grounding samples={na['n_grounding_samples']})"
    )


if __name__ == "__main__":
    main()
