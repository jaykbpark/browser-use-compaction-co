#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from browserdelta.external.browsergym_adapter import (  # noqa: E402
    BrowserGymUnavailable,
    record_episode,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record one BrowserGym/MiniWoB episode as a BrowserDelta run."
    )
    parser.add_argument("--env", required=True, help="Example: browsergym/miniwob.click-button")
    parser.add_argument("--run-id", required=True, help="Output run id under RUNS_DIR/runs.")
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument(
        "--action",
        action="append",
        default=None,
        help="Scripted BrowserGym action, repeatable. Example: --action \"click('a12')\"",
    )
    parser.add_argument(
        "--allow-noop-policy",
        action="store_true",
        help="Record a no-op smoke trace when no scripted actions are supplied.",
    )
    args = parser.parse_args(argv)

    if not args.action and not args.allow_noop_policy:
        parser.error(
            "BrowserGym recording needs --action for a meaningful eval. "
            "Use --allow-noop-policy only for adapter smoke tests."
        )

    try:
        run_path = record_episode(
            args.env,
            args.run_id,
            max_steps=args.max_steps,
            headless=args.headless,
            actions=args.action,
            compact=args.compact,
        )
    except BrowserGymUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"recorded {args.env} -> {run_path}")
    if args.compact:
        print(f"compact observations: {run_path / 'compact_observations.jsonl'}")
    if not args.action:
        print("warning: no-op policy trace; do not use this as a task-success benchmark")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
