#!/usr/bin/env python3
"""Aggregate multi-seed BrowserGym/MiniWoB live-eval reports into demo summaries.

Reads the per-seed JSON reports written by ``scripts/run_browsergym_live.py``
(one report per ``reports/external/miniwob-5seed/seed-<N>/`` directory) and emits:

- ``summary.json`` : machine-readable aggregate (means/stds, reductions, counts)
- ``summary.md``   : demo-ready human summary
- ``success_rate_bar.png``, ``token_usage_bar.png``, ``failure_classes_bar.png``

The aggregator never reads raw run artifacts; it only consumes the report JSON,
so it can run from the base environment without the BrowserGym stack.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

FAILURE_CLASSES = [
    "both_success",
    "compact_only_success",
    "compact_regression",
    "both_failed",
    "runner_error",
    "missing_mode",
]


def _mode_row(report: dict[str, Any], mode: str) -> dict[str, Any]:
    for row in report["summary"]["by_mode"]:
        if row["mode"] == mode:
            return row
    return {"success_rate": 0.0, "avg_decision_tokens": 0.0, "successes": 0, "episodes": 0}


def _latest_report(seed_dir: Path) -> Path | None:
    candidates = sorted(seed_dir.glob("*.json"))
    return candidates[-1] if candidates else None


def _mean_std(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "std": 0.0, "n": 0}
    return {
        "mean": round(statistics.fmean(values), 4),
        "std": round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0,
        "n": len(values),
    }


def load_seeds(in_dir: Path) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    for seed_dir in sorted(in_dir.glob("seed-*")):
        if not seed_dir.is_dir():
            continue
        report_path = _latest_report(seed_dir)
        if report_path is None:
            print(f"warning: no JSON report in {seed_dir}, skipping")
            continue
        report = json.loads(report_path.read_text())
        seed_id = seed_dir.name.split("-", 1)[-1]
        compact = _mode_row(report, "compact")
        full_state = _mode_row(report, "full_state")
        compact_avg = float(compact["avg_decision_tokens"])
        full_avg = float(full_state["avg_decision_tokens"])
        reduction = round((full_avg - compact_avg) / full_avg * 100, 2) if full_avg else 0.0
        seeds.append(
            {
                "seed": seed_id,
                "report_path": str(report_path),
                "episodes": report["summary"]["episodes"],
                "compact_success_rate": float(compact["success_rate"]),
                "full_state_success_rate": float(full_state["success_rate"]),
                "compact_avg_tokens": compact_avg,
                "full_state_avg_tokens": full_avg,
                "token_reduction_pct": reduction,
                "failure_classes": dict(report["summary"]["failure_classes"]),
                "failure_table": report["failure_table"],
            }
        )
    return seeds


def aggregate(seeds: list[dict[str, Any]]) -> dict[str, Any]:
    class_totals: Counter[str] = Counter()
    regression_freq: Counter[str] = Counter()
    compact_only_freq: Counter[str] = Counter()
    for seed in seeds:
        for name, count in seed["failure_classes"].items():
            class_totals[name] += count
        for row in seed["failure_table"]:
            env = row["env_id"]
            if row["failure_class"] == "compact_regression":
                regression_freq[env] += 1
            elif row["failure_class"] == "compact_only_success":
                compact_only_freq[env] += 1

    task_counts = sorted({seed["episodes"] for seed in seeds})
    return {
        "seeds": [s["seed"] for s in seeds],
        "num_seeds": len(seeds),
        "tasks_per_seed": task_counts[0] if len(task_counts) == 1 else task_counts,
        "consistent_task_count": len(task_counts) == 1,
        "compact_success_rate": _mean_std([s["compact_success_rate"] for s in seeds]),
        "full_state_success_rate": _mean_std([s["full_state_success_rate"] for s in seeds]),
        "compact_avg_tokens": _mean_std([s["compact_avg_tokens"] for s in seeds]),
        "full_state_avg_tokens": _mean_std([s["full_state_avg_tokens"] for s in seeds]),
        "token_reduction_pct": _mean_std([s["token_reduction_pct"] for s in seeds]),
        "failure_class_totals": {name: class_totals.get(name, 0) for name in FAILURE_CLASSES},
        "top_compact_regressions": [
            {"env_id": env, "seeds": n} for env, n in regression_freq.most_common(10)
        ],
        "top_compact_only_wins": [
            {"env_id": env, "seeds": n} for env, n in compact_only_freq.most_common(10)
        ],
    }


def write_charts(agg: dict[str, Any], out_dir: Path) -> list[Path]:
    paths: list[Path] = []

    # 1. Success rate bar (compact vs full_state, mean +/- std)
    fig, ax = plt.subplots(figsize=(6, 4))
    labels = ["compact", "full_state"]
    means = [
        agg["compact_success_rate"]["mean"] * 100,
        agg["full_state_success_rate"]["mean"] * 100,
    ]
    errs = [
        agg["compact_success_rate"]["std"] * 100,
        agg["full_state_success_rate"]["std"] * 100,
    ]
    bars = ax.bar(labels, means, yerr=errs, capsize=8, color=["#2b8cbe", "#888888"])
    ax.set_ylabel("Success rate (%)")
    ax.set_title(f"MiniWoB success rate by mode ({agg['num_seeds']} seeds)")
    ax.set_ylim(0, max(m + e for m, e in zip(means, errs)) * 1.25 + 1)
    for bar, mean, err in zip(bars, means, errs):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + err + 0.8,
                f"{mean:.1f}%", ha="center", va="bottom")
    fig.tight_layout()
    p = out_dir / "success_rate_bar.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(p)

    # 2. Token usage bar (compact vs full_state, mean +/- std)
    fig, ax = plt.subplots(figsize=(6, 4))
    means = [agg["compact_avg_tokens"]["mean"], agg["full_state_avg_tokens"]["mean"]]
    errs = [agg["compact_avg_tokens"]["std"], agg["full_state_avg_tokens"]["std"]]
    bars = ax.bar(labels, means, yerr=errs, capsize=8, color=["#2b8cbe", "#888888"])
    ax.set_ylabel("Avg decision tokens / episode")
    ax.set_title(
        f"MiniWoB token usage by mode "
        f"(-{agg['token_reduction_pct']['mean']:.1f}% compact)"
    )
    ax.set_ylim(0, max(m + e for m, e in zip(means, errs)) * 1.2 + 1)
    for bar, mean, err in zip(bars, means, errs):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + err + 30,
                f"{mean:.0f}", ha="center", va="bottom")
    fig.tight_layout()
    p = out_dir / "token_usage_bar.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(p)

    # 3. Failure classes bar (totals across seeds)
    fig, ax = plt.subplots(figsize=(7, 4))
    totals = agg["failure_class_totals"]
    names = [n for n in FAILURE_CLASSES if totals.get(n, 0) > 0]
    counts = [totals[n] for n in names]
    colors = {
        "both_success": "#1a9850",
        "compact_only_success": "#66bd63",
        "compact_regression": "#d73027",
        "both_failed": "#bbbbbb",
        "runner_error": "#000000",
        "missing_mode": "#fdae61",
    }
    bars = ax.bar(names, counts, color=[colors.get(n, "#888888") for n in names])
    ax.set_ylabel("Episodes (summed over seeds)")
    ax.set_title("Compact-vs-full_state outcome classes")
    ax.tick_params(axis="x", rotation=20)
    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), str(count),
                ha="center", va="bottom")
    fig.tight_layout()
    p = out_dir / "failure_classes_bar.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    paths.append(p)

    return paths


def write_markdown(agg: dict[str, Any], seeds: list[dict[str, Any]], out_dir: Path,
                   subset_rule: str) -> Path:
    def ms(d: dict[str, Any], scale: float = 1.0, unit: str = "") -> str:
        return f"{d['mean'] * scale:.2f}{unit} \u00b1 {d['std'] * scale:.2f}{unit}"

    lines: list[str] = []
    lines.append("# MiniWoB 5-Seed BrowserDelta Benchmark\n")
    lines.append(
        f"Compact (BrowserDelta) vs full_state observations on MiniWoB, "
        f"policy=llm, headless, max-steps=8, seeds={', '.join(agg['seeds'])}.\n"
    )
    lines.append(f"**Tasks per seed:** {agg['tasks_per_seed']}  ")
    lines.append(f"**Subset rule:** {subset_rule}\n")

    lines.append("## Headline numbers (mean \u00b1 std across seeds)\n")
    lines.append("| Metric | compact | full_state |")
    lines.append("| --- | --- | --- |")
    lines.append(
        f"| Success rate | {ms(agg['compact_success_rate'], 100, '%')} "
        f"| {ms(agg['full_state_success_rate'], 100, '%')} |"
    )
    lines.append(
        f"| Avg decision tokens | {ms(agg['compact_avg_tokens'])} "
        f"| {ms(agg['full_state_avg_tokens'])} |"
    )
    lines.append("")
    lines.append(
        f"**Average token reduction (compact vs full_state):** "
        f"{ms(agg['token_reduction_pct'], 1, '%')}\n"
    )

    lines.append("## Outcome classes (summed across seeds)\n")
    lines.append("| Class | Episodes |")
    lines.append("| --- | --- |")
    for name in FAILURE_CLASSES:
        count = agg["failure_class_totals"].get(name, 0)
        if count:
            lines.append(f"| {name} | {count} |")
    lines.append("")

    lines.append("## Top compact regressions (by frequency across seeds)\n")
    if agg["top_compact_regressions"]:
        lines.append("| Task | Seeds regressed |")
        lines.append("| --- | --- |")
        for row in agg["top_compact_regressions"]:
            lines.append(f"| {row['env_id']} | {row['seeds']} |")
    else:
        lines.append("_None._")
    lines.append("")

    lines.append("## Top compact-only wins (by frequency across seeds)\n")
    if agg["top_compact_only_wins"]:
        lines.append("| Task | Seeds won |")
        lines.append("| --- | --- |")
        for row in agg["top_compact_only_wins"]:
            lines.append(f"| {row['env_id']} | {row['seeds']} |")
    else:
        lines.append("_None._")
    lines.append("")

    lines.append("## Per-seed detail\n")
    lines.append("| Seed | Tasks | compact succ | full_state succ | compact tok | full_state tok | reduction |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for s in seeds:
        lines.append(
            f"| {s['seed']} | {s['episodes']} "
            f"| {s['compact_success_rate'] * 100:.1f}% "
            f"| {s['full_state_success_rate'] * 100:.1f}% "
            f"| {s['compact_avg_tokens']:.0f} "
            f"| {s['full_state_avg_tokens']:.0f} "
            f"| {s['token_reduction_pct']:.1f}% |"
        )
    lines.append("")

    lines.append("## Charts\n")
    lines.append("![Success rate](success_rate_bar.png)")
    lines.append("![Token usage](token_usage_bar.png)")
    lines.append("![Failure classes](failure_classes_bar.png)")
    lines.append("")

    p = out_dir / "summary.md"
    p.write_text("\n".join(lines) + "\n")
    return p


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--in-dir",
        type=Path,
        default=root / "reports" / "external" / "miniwob-5seed",
        help="Directory containing seed-<N>/ report folders.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=root / "reports" / "demo" / "miniwob-5seed-summary",
        help="Output directory for summary.json, summary.md, and charts.",
    )
    parser.add_argument(
        "--subset-rule",
        default="Full MiniWoB suite: all 125 registered browsergym/miniwob.* tasks per seed.",
        help="Human-readable description of which task subset was run.",
    )
    args = parser.parse_args(argv)

    seeds = load_seeds(args.in_dir)
    if not seeds:
        raise SystemExit(f"No seed reports found under {args.in_dir}")

    agg = aggregate(seeds)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "benchmark": "miniwob-5seed",
        "policy": "llm",
        "modes": ["compact", "full_state"],
        "max_steps": 8,
        "subset_rule": args.subset_rule,
        "aggregate": agg,
        "per_seed": [
            {k: v for k, v in s.items() if k != "failure_table"} for s in seeds
        ],
    }
    summary_path = args.out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")

    md_path = write_markdown(agg, seeds, args.out_dir, args.subset_rule)
    chart_paths = write_charts(agg, args.out_dir)

    print(f"wrote {summary_path}")
    print(f"wrote {md_path}")
    for p in chart_paths:
        print(f"wrote {p}")
    print(
        f"compact success {agg['compact_success_rate']['mean'] * 100:.1f}% vs "
        f"full_state {agg['full_state_success_rate']['mean'] * 100:.1f}% | "
        f"token reduction {agg['token_reduction_pct']['mean']:.1f}%"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
