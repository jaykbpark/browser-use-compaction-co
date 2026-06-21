"""External benchmark suite runner: compact vs full/vision observation modes.

Records a few BrowserGym/MiniWoB++ episodes, runs the BrowserDelta evaluator on
each, and aggregates token/savings/success metrics across the three observation
modes the project compares:

* ``vision_full_state`` -- full page state text + a screenshot every step (baseline)
* ``full_state``        -- full page state text only, no screenshot
* ``compact``           -- BrowserDelta compact observation (text, crops on fallback)

The recording step needs the optional ``external-evals`` extra (BrowserGym) and a
MiniWoB server; aggregation is dependency-free and unit tested.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from browserdelta.eval.ab import EvalConfig, evaluate_run

# A small, light default MiniWoB++ task list (BrowserGym env ids).
DEFAULT_MINIWOB_SUITE = [
    "browsergym/miniwob.click-button",
    "browsergym/miniwob.click-test",
    "browsergym/miniwob.focus-text",
    "browsergym/miniwob.enter-text",
    "browsergym/miniwob.click-dialog",
]


def _mode_tokens(eval_report: dict[str, Any]) -> dict[str, int]:
    """Derive per-observation-mode token totals from an evaluate_run report."""

    steps = eval_report.get("steps", [])
    vision_full_state = sum(s["tokens_baseline"]["total"] for s in steps)
    full_state = sum(s["tokens_baseline"]["text"] for s in steps)
    compact = sum(s["tokens_compact"]["total"] for s in steps)
    return {
        "vision_full_state": vision_full_state,
        "full_state": full_state,
        "compact": compact,
    }


def _savings(baseline: int, compact: int) -> float:
    if baseline <= 0:
        return 0.0
    return round(100.0 * (baseline - compact) / baseline, 2)


def per_run_metrics(
    env_id: str,
    run_id: str,
    eval_report: dict[str, Any],
    episode_meta: dict[str, Any],
    latency_s: float,
) -> dict[str, Any]:
    summary = eval_report["summary"]
    tokens = _mode_tokens(eval_report)
    next_action = summary["next_action"]
    return {
        "env_id": env_id,
        "run_id": run_id,
        "n_steps": summary["n_steps"],
        "success": bool(episode_meta.get("success", False)),
        "reward": float(episode_meta.get("reward", 0.0)),
        "latency_s": round(latency_s, 3),
        "tokens": tokens,
        "next_action": {
            "vision_full_state": next_action.get("baseline_accuracy"),
            "full_state": next_action.get("baseline_accuracy"),
            "compact": next_action.get("compact_accuracy"),
        },
        "routes_compact": summary["routes_compact"],
        "fallback_rate": summary["fallback"]["fallback_rate"],
    }


def aggregate_suite_report(
    per_run: list[dict[str, Any]],
    *,
    suite: str = "browsergym-miniwob",
    predictor: str = "heuristic",
) -> dict[str, Any]:
    """Aggregate per-run metrics into a suite report (dependency-free)."""

    ok = [r for r in per_run if not r.get("error")]
    failures = [{"env_id": r["env_id"], "reason": r["error"]} for r in per_run if r.get("error")]
    for r in ok:
        if not r["success"]:
            failures.append({"env_id": r["env_id"], "reason": "episode_not_solved"})

    n_steps = sum(r["n_steps"] for r in ok)
    modes = ("vision_full_state", "full_state", "compact")
    totals = {m: sum(r["tokens"][m] for r in ok) for m in modes}

    def _mean_acc(mode: str) -> float | None:
        vals = [r["next_action"][mode] for r in ok if r["next_action"][mode] is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    latencies = [r["latency_s"] for r in ok if r.get("latency_s") is not None]

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suite": suite,
        "predictor": predictor,
        "n_tasks": len(per_run),
        "n_tasks_ok": len(ok),
        "n_steps": n_steps,
        "success_rate": round(sum(r["success"] for r in ok) / len(ok), 3) if ok else None,
        "tokens": {
            "totals": totals,
            "savings_pct": {
                "compact_vs_vision_full_state": _savings(
                    totals["vision_full_state"], totals["compact"]
                ),
                "compact_vs_full_state": _savings(totals["full_state"], totals["compact"]),
            },
        },
        "next_action_accuracy": {m: _mean_acc(m) for m in modes},
        "mean_latency_s": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "failures": failures,
        "runs": per_run,
    }


def run_suite(
    env_ids: list[str] | None = None,
    *,
    predictor: str = "heuristic",
    max_steps: int = 10,
    headless: bool = True,
    out_dir: Path | None = None,
    config: EvalConfig | None = None,
) -> dict[str, Any]:
    """Record + evaluate each env, then aggregate. Requires the external extra."""

    from browserdelta.external.browsergym_adapter import record_episode

    env_ids = env_ids or DEFAULT_MINIWOB_SUITE
    per_run: list[dict[str, Any]] = []

    for env_id in env_ids:
        run_id = "bg_" + env_id.split(".")[-1].replace("-", "_")
        try:
            start = time.time()
            run_path = record_episode(
                env_id, run_id, max_steps=max_steps, headless=headless, compact=True
            )
            latency = time.time() - start
            eval_report = evaluate_run(run_path, predictor=predictor, config=config)
            meta = json.loads((run_path / "run.json").read_text()).get("metadata", {})
            per_run.append(per_run_metrics(env_id, run_id, eval_report, meta, latency))
        except Exception as exc:  # noqa: BLE001 - record per-task failure, keep going
            per_run.append(
                {"env_id": env_id, "run_id": run_id, "error": f"{type(exc).__name__}: {exc}"}
            )

    report = aggregate_suite_report(per_run, predictor=predictor)

    out_dir = out_dir or (Path("reports") / "external")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"browsergym-miniwob_{predictor}_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    report["_report_path"] = str(out_path)
    return report
