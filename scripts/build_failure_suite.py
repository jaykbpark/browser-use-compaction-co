#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_FAILURE_CLASSES = ("compact_regression", "both_failed")
NON_SUCCESS_CLASSES = (
    "compact_regression",
    "both_failed",
    "compact_only_success",
    "runner_error",
    "missing_mode",
)


def build_failure_suite(
    report: dict[str, Any],
    *,
    source_report: str | None = None,
    failure_classes: list[str] | None = None,
    limit: int | None = None,
    run_prefix: str = "failure_loop",
    suite_name: str | None = None,
) -> dict[str, Any]:
    selected_classes = failure_classes or list(DEFAULT_FAILURE_CLASSES)
    wanted = set(selected_classes)
    rows = report.get("failure_table")
    if not isinstance(rows, list):
        raise ValueError("Report must include a failure_table list.")

    runs_by_id = {
        str(run.get("run_id")): run
        for run in report.get("runs", [])
        if isinstance(run, dict) and run.get("run_id")
    }

    episodes: list[dict[str, Any]] = []
    seen_run_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        failure_class = str(row.get("failure_class") or "")
        if failure_class not in wanted:
            continue
        env_id = str(row.get("env_id") or "")
        if not env_id:
            continue
        source_run = (
            runs_by_id.get(str(row.get("compact_run_id")))
            or runs_by_id.get(str(row.get("baseline_run_id")))
            or {}
        )
        episode = {
            "env_id": env_id,
            "run_id": _unique_run_id(run_prefix, env_id, seen_run_ids),
            "metadata": {
                "source_failure_class": failure_class,
                "source_compact_success": row.get("compact_success"),
                "source_baseline_success": row.get("baseline_success"),
                "source_token_reduction_pct": row.get("token_reduction_pct"),
            },
        }
        goal = source_run.get("goal")
        if goal:
            episode["goal"] = str(goal)
        max_steps = max(
            int(row.get("compact_steps") or 0),
            int(row.get("baseline_steps") or 0),
            int(source_run.get("steps") or 0),
        )
        if max_steps:
            episode["max_steps"] = max_steps
        episodes.append(episode)
        if limit is not None and len(episodes) >= limit:
            break

    source_suite = str(report.get("suite") or "browsergym-live")
    return {
        "schema_version": 1,
        "suite": suite_name or f"{source_suite}-failure-loop",
        "source": "browserdelta-failure-loop",
        "source_report": source_report,
        "selected_failure_classes": selected_classes,
        "source_summary": report.get("summary", {}),
        "episodes": episodes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a BrowserGym live suite from a BrowserDelta failure table."
    )
    parser.add_argument("report", type=Path, help="Path to a run_browsergym_live JSON report.")
    parser.add_argument(
        "--classes",
        default=",".join(DEFAULT_FAILURE_CLASSES),
        help="Comma-separated failure classes to include.",
    )
    parser.add_argument(
        "--all-non-success",
        action="store_true",
        help="Include every non-both_success class, including compact_only_success.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", type=Path, default=None, help="Write suite JSON here.")
    parser.add_argument("--run-prefix", default="failure_loop")
    parser.add_argument("--suite-name", default=None)
    args = parser.parse_args(argv)

    report = json.loads(args.report.read_text())
    classes = (
        list(NON_SUCCESS_CLASSES)
        if args.all_non_success
        else [item.strip() for item in args.classes.split(",") if item.strip()]
    )
    suite = build_failure_suite(
        report,
        source_report=str(args.report),
        failure_classes=classes,
        limit=args.limit,
        run_prefix=args.run_prefix,
        suite_name=args.suite_name,
    )
    payload = json.dumps(suite, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload)
        print(
            f"wrote {args.out} "
            f"({len(suite['episodes'])} episodes, classes={','.join(classes)})"
        )
    else:
        print(payload, end="")
    return 0


def _unique_run_id(prefix: str, env_id: str, seen: set[str]) -> str:
    slug = env_id.rsplit("/", 1)[-1].replace(".", "_").replace("-", "_")
    base = f"{prefix}_{slug}"
    run_id = base
    suffix = 2
    while run_id in seen:
        run_id = f"{base}_{suffix}"
        suffix += 1
    seen.add(run_id)
    return run_id


if __name__ == "__main__":
    raise SystemExit(main())
