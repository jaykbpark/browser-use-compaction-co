#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from browserdelta.eval.runner import evaluate_comparison, evaluate_run  # noqa: E402
from browserdelta.external.browsergym_adapter import (  # noqa: E402
    BrowserGymUnavailable,
    record_episode,
)
from eval_suite import (  # noqa: E402
    summarize_comparison,
    summarize_comparison_rows,
    summarize_report,
    summarize_rows,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record scripted BrowserGym episodes and evaluate BrowserDelta compaction."
    )
    parser.add_argument("suite", type=Path, help="JSON file with an episodes list.")
    parser.add_argument("--predictor", default="heuristic", choices=["heuristic", "llm"])
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--no-compact", dest="compact", action="store_false")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument(
        "--baseline-context",
        default="vision_full_state",
        choices=["full_state", "vision_full_state"],
    )
    parser.add_argument(
        "--allow-noop-policy",
        action="store_true",
        help="Allow suite entries without scripted actions; useful only for smoke traces.",
    )
    parser.add_argument("--out-dir", type=Path, default=ROOT / "reports" / "external")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    suite = _load_suite(args.suite)
    try:
        report = run_external_suite(
            suite,
            predictor=args.predictor,
            max_steps=args.max_steps,
            headless=args.headless,
            compact=args.compact,
            compare=args.compare,
            baseline_context_mode=args.baseline_context,
            allow_noop_policy=args.allow_noop_policy,
        )
    except BrowserGymUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out_dir / f"{report['suite']}_{report['predictor']}_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        summary = report["summary"]
        print(f"wrote {out_path}")
        print(
            f"episodes={summary['runs']} compact_tokens={summary['compact_tokens']} "
            f"baseline_tokens={summary['baseline_tokens']}"
        )
        if args.compare:
            print(
                f"compact={summary['compact_passed_evaluated']} "
                f"baseline={summary['baseline_passed_evaluated']} "
                f"saved={summary['token_reduction_pct']:.2f}%"
            )
        else:
            print(
                f"accuracy={summary['accuracy'] * 100:.1f}% "
                f"avg_saved={summary['avg_reduction_pct']:.2f}%"
            )
    return 0


def run_external_suite(
    suite: dict[str, Any],
    *,
    predictor: str = "heuristic",
    max_steps: int = 10,
    headless: bool = True,
    compact: bool = True,
    compare: bool = False,
    baseline_context_mode: str = "vision_full_state",
    allow_noop_policy: bool = False,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    episodes = suite.get("episodes")
    if not isinstance(episodes, list):
        raise ValueError("External suite JSON must include an episodes list.")

    for episode in episodes:
        if not isinstance(episode, dict):
            raise ValueError("Each episode must be an object.")
        env_id = str(episode["env_id"])
        run_id = str(episode.get("run_id") or _run_id_from_env(env_id))
        actions = [str(action) for action in episode.get("actions") or []]
        if not actions and not allow_noop_policy:
            raise ValueError(
                f"{run_id} has no scripted actions. Add actions or pass --allow-noop-policy."
            )

        run_path = record_episode(
            env_id,
            run_id,
            max_steps=int(episode.get("max_steps") or max_steps),
            headless=headless,
            actions=actions or None,
            compact=compact,
        )
        goal = str(episode.get("goal") or "")
        if compare:
            rows.append(
                summarize_comparison(
                    evaluate_comparison(
                        run_path,
                        goal=goal,
                        predictor=predictor,
                        baseline_context_mode=baseline_context_mode,  # type: ignore[arg-type]
                    )
                )
            )
        else:
            rows.append(summarize_report(evaluate_run(run_path, goal=goal, predictor=predictor)))

    return {
        "schema_version": 1,
        "suite": str(suite.get("suite") or "external-browsergym"),
        "source": "browsergym",
        "predictor": predictor,
        "mode": "comparison" if compare else "compact",
        "runs": rows,
        "summary": summarize_comparison_rows(rows) if compare else summarize_rows(rows),
    }


def _load_suite(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("External suite JSON must be an object.")
    return data


def _run_id_from_env(env_id: str) -> str:
    return "bg_" + env_id.rsplit(".", 1)[-1].replace("-", "_").replace("/", "_")


if __name__ == "__main__":
    raise SystemExit(main())
