"""Run an external benchmark suite and compare observation modes.

Records a small BrowserGym/MiniWoB++ task list, evaluates each episode, and
writes an aggregate report (compact vs full_state vs vision_full_state) under
``reports/external/`` (gitignored). Example:

    python scripts/eval_external_suite.py --suite browsergym-miniwob \\
        --predictor llm --compare

Requires the optional ``external-evals`` extra and a MiniWoB server.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from browserdelta.external.browsergym_adapter import BrowserGymUnavailable  # noqa: E402
from browserdelta.external.suite import DEFAULT_MINIWOB_SUITE, run_suite  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="browsergym-miniwob", choices=["browsergym-miniwob"])
    parser.add_argument("--predictor", default="heuristic", choices=["heuristic", "llm"])
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--no-headless", dest="headless", action="store_false")
    parser.add_argument(
        "--env",
        action="append",
        default=None,
        help="override the default task list (repeatable env ids)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="print the compact-vs-full/vision comparison summary",
    )
    args = parser.parse_args()

    env_ids = args.env or DEFAULT_MINIWOB_SUITE
    try:
        report = run_suite(
            env_ids,
            predictor=args.predictor,
            max_steps=args.max_steps,
            headless=args.headless,
        )
    except BrowserGymUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"report written to {report['_report_path']}")
    if args.compare:
        tokens = report["tokens"]
        print(
            json.dumps(
                {
                    "suite": report["suite"],
                    "predictor": report["predictor"],
                    "n_tasks_ok": report["n_tasks_ok"],
                    "success_rate": report["success_rate"],
                    "token_totals": tokens["totals"],
                    "savings_pct": tokens["savings_pct"],
                    "next_action_accuracy": report["next_action_accuracy"],
                    "failures": report["failures"],
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
