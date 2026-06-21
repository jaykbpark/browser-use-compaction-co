"""``browserdelta`` command line interface.

A single entry point so other agents (or humans) can drive BrowserDelta without
the repo checkout:

    browserdelta serve                      # run the API + viewer backend
    browserdelta record --task task.json    # record + compact a scripted task
    browserdelta demo                       # generate local demo dashboard runs
    browserdelta compact <run>              # (re)compact a recorded run
    browserdelta eval <run> --compare       # score next-action parity vs baseline
    browserdelta observe <run>              # print the agent-facing compact JSON
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from browserdelta import __version__


DEFAULT_DEMO_TASKS = [
    "local_checkout",
    "search_filter",
    "visual_canvas_chart",
    "visual_progress_toast",
    "visual_swatch_picker",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="browserdelta",
        description="Semantic context compaction for browser agents.",
    )
    parser.add_argument("--version", action="version", version=f"browserdelta {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="Run the BrowserDelta API/viewer backend.")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=_cmd_serve)

    p_demo = sub.add_parser("demo", help="Generate local screenshot-rich dashboard runs.")
    p_demo.add_argument(
        "--task",
        action="append",
        dest="tasks",
        help="Task id or task JSON path. Defaults to the local demo suite.",
    )
    p_demo.add_argument("--runtime", choices=["auto", "local", "browserbase"], default="local")
    p_demo.add_argument("--headed", action="store_true", help="Show the browser window.")
    p_demo.add_argument("--skip-eval", action="store_true", help="Skip heuristic comparison eval.")
    p_demo.add_argument("--predictor", default="heuristic", choices=["heuristic", "llm"])
    p_demo.add_argument(
        "--baseline-context",
        default="vision_full_state",
        choices=["full_state", "vision_full_state"],
    )
    p_demo.set_defaults(func=_cmd_demo)

    p_record = sub.add_parser("record", help="Record a scripted task and compact it.")
    p_record.add_argument(
        "--task",
        type=Path,
        required=True,
        help="Task JSON (start_url + actions).",
    )
    p_record.add_argument("--run-id", help="Run folder name. Defaults to the task id.")
    p_record.add_argument("--runtime", choices=["auto", "local", "browserbase"], default="auto")
    p_record.add_argument("--headless", action="store_true")
    p_record.add_argument("--json", action="store_true", help="Print compact observations as JSON.")
    p_record.set_defaults(func=_cmd_record)

    p_compact = sub.add_parser("compact", help="(Re)compact a recorded run.")
    p_compact.add_argument("run", help="Run folder path or run id under RUNS_DIR.")
    p_compact.add_argument("--json", action="store_true")
    p_compact.set_defaults(func=_cmd_compact)

    p_eval = sub.add_parser("eval", help="Replay-evaluate a compacted run.")
    p_eval.add_argument("run", help="Run folder path or run id under RUNS_DIR.")
    p_eval.add_argument("--predictor", default="heuristic", choices=["heuristic", "llm"])
    p_eval.add_argument(
        "--context-mode", default="compact", choices=["compact", "full_state", "vision_full_state"]
    )
    p_eval.add_argument("--compare", action="store_true", help="Compare vs a baseline context.")
    p_eval.add_argument(
        "--baseline-context",
        default="vision_full_state",
        choices=["full_state", "vision_full_state"],
    )
    p_eval.add_argument("--json", action="store_true")
    p_eval.set_defaults(func=_cmd_eval)

    p_observe = sub.add_parser(
        "observe", help="Print compact observations for a CLI agent."
    )
    p_observe.add_argument("run", help="Run folder path or run id under RUNS_DIR.")
    p_observe.add_argument("--step", type=int, help="Only emit this step.")
    p_observe.add_argument("--format", choices=["agent", "json"], default="json")
    p_observe.add_argument("--all", action="store_true", help="Emit every compact step.")
    p_observe.add_argument(
        "--absolute-paths",
        action="store_true",
        help="Emit absolute artifact paths instead of run-relative paths.",
    )
    p_observe.set_defaults(func=_cmd_observe)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("browserdelta.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    from browserdelta.eval.runner import evaluate_comparison
    from browserdelta.sdk import record_task

    run_paths: list[Path] = []
    for value in args.tasks or DEFAULT_DEMO_TASKS:
        task_path = _task_path(value)
        task = _load_task(task_path)
        run_path, observations = asyncio.run(
            record_task(
                task,
                run_id=task.get("id"),
                headless=not args.headed,
                runtime=args.runtime,
            )
        )
        run_paths.append(run_path)
        print(f"recorded {len(observations)} steps -> {run_path}")

    if not args.skip_eval:
        print("\ncomparison")
        for run_path in run_paths:
            report = evaluate_comparison(
                run_path,
                predictor=args.predictor,
                baseline_context_mode=args.baseline_context,  # type: ignore[arg-type]
            )
            s = report.summary
            print(
                f"{report.run_id}: compact {s.compact_passed_steps}/{s.evaluated_steps}, "
                f"baseline {s.baseline_passed_steps}/{s.evaluated_steps}, "
                f"{s.token_reduction_pct:.1f}% fewer tokens"
            )

    print("\nready")
    print("browserdelta serve")
    print("npm --prefix viewer run dev -- --host 127.0.0.1 --port 5174")
    print("open http://127.0.0.1:5174/#dashboard")
    return 0


def _cmd_record(args: argparse.Namespace) -> int:
    from browserdelta.sdk import record_task

    task = _load_task(args.task)
    run_path, observations = asyncio.run(
        record_task(task, run_id=args.run_id, headless=args.headless, runtime=args.runtime)
    )
    if args.json:
        print(json.dumps([_observe_payload(o) for o in observations], indent=2))
        return 0
    print(f"recorded {len(observations)} steps -> {run_path}")
    for obs in observations:
        print(f"  step {obs.step}: {obs.route}  −{obs.reduction_pct:.0f}%  {obs.summary}")
    return 0


def _cmd_compact(args: argparse.Namespace) -> int:
    from browserdelta.compaction.codec import compact_run

    run_path = _resolve_run(args.run)
    observations = compact_run(run_path)
    if args.json:
        print(json.dumps([_observe_payload(o) for o in observations], indent=2))
        return 0
    print(f"compacted {len(observations)} steps in {run_path}")
    for obs in observations:
        print(f"  step {obs.step}: {obs.route}  −{obs.reduction_pct:.0f}%  {obs.summary}")
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    from browserdelta.eval.runner import evaluate_comparison, evaluate_run

    run_path = _resolve_run(args.run)
    if args.compare:
        report = evaluate_comparison(
            run_path,
            predictor=args.predictor,
            baseline_context_mode=args.baseline_context,  # type: ignore[arg-type]
        )
        if args.json:
            print(json.dumps(report.model_dump(mode="json"), indent=2))
            return 0
        s = report.summary
        print(
            f"compact {s.compact_passed_steps}/{s.evaluated_steps} vs "
            f"{s.baseline_context_mode} {s.baseline_passed_steps}/{s.evaluated_steps} · "
            f"{s.token_reduction_pct:.1f}% fewer tokens"
        )
        print(f"verdict: {report.verdict}")
        return 0

    report = evaluate_run(
        run_path,
        predictor=args.predictor,
        context_mode=args.context_mode,  # type: ignore[arg-type]
    )
    if args.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
        return 0
    print(
        f"{report.passed_steps}/{report.evaluated_steps} next actions matched "
        f"({report.next_action_accuracy * 100:.1f}%) · {report.avg_reduction_pct:.1f}% avg saved"
    )
    return 0


def _cmd_observe(args: argparse.Namespace) -> int:
    from browserdelta.compaction.codec import compact_run

    run_path = _resolve_run(args.run)
    obs_path = run_path / "compact_observations.jsonl"
    if not obs_path.exists():
        compact_run(run_path)

    if args.all:
        payload: Any = build_observation_payloads(
            run_path,
            absolute_paths=args.absolute_paths,
        )
    else:
        payload = build_observation_payload(
            run_path,
            step=args.step,
            absolute_paths=args.absolute_paths,
        )

    if args.format == "agent":
        if isinstance(payload, list):
            print("\n\n".join(format_agent_observation(item) for item in payload))
        else:
            print(format_agent_observation(payload))
        return 0

    print(json.dumps(payload, indent=2))
    return 0


_AGENT_FIELDS = (
    "step",
    "summary",
    "llm_observation",
    "route",
    "fallback",
    "tokens_estimate",
    "baseline_tokens_estimate",
    "reduction_pct",
    "crop_paths",
    "full_screenshot_path",
)


def _observe_payload(observation: Any) -> dict[str, Any]:
    return _observe_payload_dict(observation.model_dump(mode="json"))


def _observe_payload_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in _AGENT_FIELDS}


def build_observation_payloads(
    run_path: Path,
    absolute_paths: bool = False,
) -> list[dict[str, Any]]:
    from browserdelta.schemas import CompactObservation
    from browserdelta.storage import read_jsonl, read_steps

    run_path = _resolve_run(str(run_path))
    rows = read_jsonl(run_path / "compact_observations.jsonl")
    if not rows:
        raise ValueError(f"No compact observations found in {run_path}.")
    steps = {record.step: record for record in read_steps(run_path)}
    return [
        _agent_payload_from_observation(
            run_path,
            CompactObservation.model_validate(row),
            after_screenshot=(
                steps[row["step"]].after.screenshot if row["step"] in steps else None
            ),
            absolute_paths=absolute_paths,
        )
        for row in rows
    ]


def build_observation_payload(
    run_path: Path,
    step: int | None = None,
    absolute_paths: bool = False,
) -> dict[str, Any]:
    payloads = build_observation_payloads(run_path, absolute_paths=absolute_paths)
    if step is None:
        return payloads[-1]
    for payload in payloads:
        if payload["step"] == step:
            return payload
    raise ValueError(f"step {step} not found in {run_path}")


def format_agent_observation(payload: dict[str, Any]) -> str:
    lines = [
        f"BrowserDelta observation: {payload['run_id']} step {payload['step']}",
        (
            f"route={payload['route']} fallback={payload['fallback']} "
            f"tokens={payload['tokens_estimate']}/{payload['baseline_tokens_estimate']} "
            f"saved={payload['reduction_pct']:.2f}%"
        ),
        "",
        payload["llm_observation"],
    ]
    artifacts = payload["artifacts"]
    crop_paths = [path for path in artifacts["crop_paths"] if path]
    if crop_paths or artifacts["full_screenshot_path"]:
        lines.append("")
        lines.append("visual artifacts")
        for path in crop_paths:
            lines.append(f"- crop: {path}")
        if artifacts["full_screenshot_path"]:
            lines.append(f"- full_screenshot: {artifacts['full_screenshot_path']}")
    return "\n".join(lines)


def _agent_payload_from_observation(
    run_path: Path,
    observation: Any,
    after_screenshot: str | None,
    absolute_paths: bool,
) -> dict[str, Any]:
    def artifact(path: str | None) -> str | None:
        if not path:
            return None
        if absolute_paths:
            return str((run_path / path).resolve())
        return path

    return {
        "run_id": run_path.name,
        "step": observation.step,
        "summary": observation.summary,
        "llm_observation": observation.llm_observation,
        "route": observation.route,
        "fallback": observation.fallback,
        "tokens_estimate": observation.tokens_estimate,
        "baseline_tokens_estimate": observation.baseline_tokens_estimate,
        "reduction_pct": observation.reduction_pct,
        "artifacts": {
            "after_screenshot": artifact(after_screenshot),
            "crop_paths": [artifact(path) for path in observation.crop_paths],
            "full_screenshot_path": artifact(observation.full_screenshot_path),
        },
    }


def _load_task(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"task file not found: {path}")
    data = json.loads(path.read_text())
    data.setdefault("id", path.stem)
    return data


def _task_path(value: str) -> Path:
    path = Path(value)
    if path.suffix == ".json" or path.exists():
        return path
    return Path("tasks") / f"{value}.json"


def _resolve_run(value: str) -> Path:
    from browserdelta.storage import runs_root

    candidate = Path(value)
    if candidate.exists():
        return candidate
    in_runs = runs_root() / value
    if in_runs.exists():
        return in_runs
    raise FileNotFoundError(f"run not found: {value} (also looked in {runs_root()})")


if __name__ == "__main__":
    raise SystemExit(main())
