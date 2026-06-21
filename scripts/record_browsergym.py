"""Record one BrowserGym / MiniWoB++ episode as a BrowserDelta run.

Requires the optional ``external-evals`` extra (BrowserGym + MiniWoB). Example:

    export MINIWOB_URL="file:///path/to/miniwob-plusplus/miniwob/html/miniwob/"
    python scripts/record_browsergym.py --env browsergym/miniwob.click-button \\
        --run-id bg_click_button --headless --compact

By default the episode uses a no-op policy (it records observation transitions
without solving the task). Pass --action one or more times to script actions,
e.g. --action "click('a12')".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from browserdelta.external.browsergym_adapter import (  # noqa: E402
    BrowserGymUnavailable,
    record_episode,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env", required=True, help="BrowserGym env id, e.g. browsergym/miniwob.click-button"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--compact", action="store_true", help="run the codec after recording")
    parser.add_argument(
        "--action",
        action="append",
        default=None,
        help="scripted BrowserGym action (repeatable); overrides the no-op policy",
    )
    args = parser.parse_args()

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
