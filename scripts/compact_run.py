#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from browserdelta.compaction.codec import compact_run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Compact a saved BrowserDelta run.")
    parser.add_argument("run_path", type=Path)
    args = parser.parse_args()

    observations = compact_run(args.run_path)
    for observation in observations:
        print(f"step {observation.step}: {observation.summary}")
    print(f"wrote {args.run_path / 'compact_observations.jsonl'}")


if __name__ == "__main__":
    main()
