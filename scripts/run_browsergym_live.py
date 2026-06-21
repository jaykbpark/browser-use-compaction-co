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

from browserdelta.config import get_settings  # noqa: E402
from browserdelta.external.browsergym_adapter import BrowserGymUnavailable  # noqa: E402
from browserdelta.external.browsergym_live import (  # noqa: E402
    BrowserGymLivePolicy,
    HeuristicBrowserGymPolicy,
    LLMBrowserGymPolicy,
    LiveMode,
    ScriptedBrowserGymPolicy,
    probe_workarena,
    run_live_suite,
    write_live_markdown_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run live BrowserGym tasks with compact vs full-state observations."
    )
    parser.add_argument("suite", nargs="?", type=Path, help="Optional live suite JSON file.")
    parser.add_argument("--env", action="append", default=[], help="BrowserGym env id.")
    parser.add_argument(
        "--suite-kind",
        default="miniwob",
        choices=["miniwob", "workarena"],
        help="Which BrowserGym env family to discover when no suite/env is supplied.",
    )
    parser.add_argument(
        "--modes",
        default="compact,full_state",
        help="Comma-separated modes: compact, full_state, vision_full_state.",
    )
    parser.add_argument("--policy", default="heuristic", choices=["heuristic", "llm", "scripted"])
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--retries", type=int, default=0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "reports" / "external")
    parser.add_argument("--probe-workarena", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.probe_workarena:
        print(json.dumps(probe_workarena(), indent=2))
        return 0

    suite = _load_suite(args.suite) if args.suite else {}
    if args.env:
        suite["episodes"] = [{"env_id": env_id} for env_id in args.env]
    suite.setdefault("suite", f"browsergym-live-{args.suite_kind}")

    settings = get_settings()
    modes = _parse_modes(args.modes)
    try:
        report = run_live_suite(
            suite,
            modes=modes,
            policy_factory=_policy_factory(args.policy, settings),
            max_steps=args.max_steps,
            headless=args.headless,
            seed=args.seed,
            retries=args.retries,
            limit=args.limit,
            suite_kind=args.suite_kind,
        )
    except BrowserGymUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = str(report["suite"]).replace("/", "_").replace(" ", "_")
    out_path = args.out_dir / f"{slug}_{args.policy}_{stamp}.json"
    md_path = out_path.with_suffix(".md")
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    write_live_markdown_report(md_path, report)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"wrote {out_path}")
        print(f"wrote {md_path}")
        for row in report["summary"]["by_mode"]:
            print(
                f"{row['mode']}: {row['successes']}/{row['episodes']} "
                f"success, avg_tokens={row['avg_decision_tokens']}"
            )
        print(f"failure_classes={report['summary']['failure_classes']}")
    return 0


def _policy_factory(
    policy_name: str,
    settings: Any,
):
    def make(mode: LiveMode, episode: dict[str, Any]) -> BrowserGymLivePolicy:
        del mode
        if policy_name == "llm":
            return LLMBrowserGymPolicy(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                base_url=settings.openai_base_url,
            )
        if policy_name == "scripted":
            actions = episode.get("actions")
            if not actions:
                raise ValueError("scripted live policy requires episode actions.")
            return ScriptedBrowserGymPolicy([str(action) for action in actions])
        return HeuristicBrowserGymPolicy()

    return make


def _parse_modes(value: str) -> list[LiveMode]:
    modes = [mode.strip() for mode in value.split(",") if mode.strip()]
    allowed = {"compact", "full_state", "vision_full_state"}
    unknown = [mode for mode in modes if mode not in allowed]
    if unknown:
        raise ValueError(f"Unknown mode(s): {', '.join(unknown)}")
    return modes  # type: ignore[return-value]


def _load_suite(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("Live BrowserGym suite must be a JSON object.")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
