#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from browserdelta.compaction.codec import compact_run  # noqa: E402
from browserdelta.schemas import CompactObservation  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Compact a saved BrowserDelta run.")
    parser.add_argument("run_path", type=Path)
    args = parser.parse_args()

    observations = compact_run(args.run_path)
    for observation in observations:
        print(format_observation_line(observation))
    if observations:
        print(format_total_line(observations))
    print(f"wrote {args.run_path / 'compact_observations.jsonl'}")


def format_observation_line(observation: CompactObservation) -> str:
    return (
        f"step {observation.step}: "
        f"{observation.route}, "
        f"{observation.reduction_pct:.2f}% saved, "
        f"confidence {observation.confidence:.2f} - "
        f"{observation.summary}"
    )


def format_total_line(observations: list[CompactObservation]) -> str:
    compact_tokens = sum(observation.tokens_estimate for observation in observations)
    baseline_tokens = sum(observation.baseline_tokens_estimate for observation in observations)
    saved_pct = 0.0
    if baseline_tokens > 0:
        saved_pct = max(0.0, (baseline_tokens - compact_tokens) / baseline_tokens * 100)
    return (
        f"total: {len(observations)} step(s), "
        f"{compact_tokens} compact tokens vs {baseline_tokens} baseline, "
        f"{saved_pct:.2f}% saved"
    )


if __name__ == "__main__":
    main()
