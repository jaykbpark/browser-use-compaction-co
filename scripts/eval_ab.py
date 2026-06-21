#!/usr/bin/env python3
"""Run the baseline-vs-compact A/B eval and write eval_report.json.

Examples:
    # Evaluate already-recorded runs under runs/.
    python scripts/eval_ab.py --tasks tasks/docs_search.json tasks/shopping.json

    # Record the runs live first (needs Playwright + network), then evaluate.
    python scripts/eval_ab.py --tasks tasks/*.json --record
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from browserdelta.config import get_settings  # noqa: E402
from browserdelta.eval.ab import run_ab_eval  # noqa: E402


def _load_tasks(task_paths: list[Path]) -> list[dict]:
    return [json.loads(path.read_text()) for path in task_paths]


async def _record_tasks(tasks: list[dict], headed: bool) -> None:
    from record_task import record_task  # noqa: E402  (scripts/ is on sys.path)

    for task in tasks:
        await record_task(task, headless=not headed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Baseline vs compact A/B eval.")
    parser.add_argument(
        "--tasks",
        nargs="+",
        type=Path,
        default=None,
        help="Task JSON files (default: every tasks/*.json).",
    )
    parser.add_argument("--runs-root", type=Path, default=None, help="Runs directory (default: RUNS_DIR).")
    parser.add_argument("--out", type=Path, default=ROOT / "eval_report.json")
    parser.add_argument("--record", action="store_true", help="Record runs live before evaluating.")
    parser.add_argument("--headed", action="store_true", help="Record with a visible browser window.")
    args = parser.parse_args()

    task_paths = args.tasks or sorted((ROOT / "tasks").glob("*.json"))
    if not task_paths:
        parser.error("no task files found")
    tasks = _load_tasks(task_paths)
    runs_root = args.runs_root or get_settings().runs_dir

    if args.record:
        sys.path.insert(0, str(ROOT / "scripts"))
        asyncio.run(_record_tasks(tasks, headed=args.headed))

    report = run_ab_eval(tasks, runs_root=runs_root)
    args.out.write_text(json.dumps(report, indent=2) + "\n")

    overall = report["overall_summary"]
    tokens = overall["tokens"]
    next_action = overall["next_action"]
    print(f"wrote {args.out}")
    print(
        f"tasks={overall['n_tasks']} steps={overall['n_steps']} "
        f"tokens baseline={tokens['baseline_total']} compact={tokens['compact_total']} "
        f"savings={tokens['savings_pct']}% ratio={tokens['compression_ratio']}x"
    )
    print(
        f"next-action accuracy baseline={next_action['baseline_accuracy']} "
        f"compact={next_action['compact_accuracy']} "
        f"(grounding samples={next_action['n_grounding_samples']})"
    )
    print(f"compact routes: {overall['routes_compact']} fallback_rate={overall['fallback']['fallback_rate']}")


if __name__ == "__main__":
    main()
