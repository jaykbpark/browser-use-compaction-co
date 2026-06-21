#!/usr/bin/env python3
"""Summarize one or more ``run_browsergym_live.py`` JSON reports.

Each input report is treated as one seed sample. When several reports are
supplied (for example one per seed) the summary reports mean success rate and
average token usage per mode together with error bars (sample standard
deviation) across the reports.

Outputs are written to ``<out-dir>/<name>/``:

- ``summary.json`` machine-readable aggregate.
- ``summary.md`` human-readable report that embeds the charts.
- ``success_rate.png`` compact vs full_state success rate (error bars if >1 seed).
- ``avg_tokens.png`` compact vs full_state average decision-token usage.
- ``failure_classes.png`` failure-class breakdown.
- ``compact_outcomes.png`` compact-only wins vs compact regressions.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

COMPACT_MODE = "compact"
DEFAULT_OUT_DIR = Path("reports") / "demo"


class ReportError(ValueError):
    """Raised when an input report is not a live BrowserGym report."""


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "summary"


def load_report(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ReportError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ReportError(f"{path} must contain a JSON object.")
    if "summary" not in data and "runs" not in data:
        raise ReportError(
            f"{path} does not look like a run_browsergym_live.py report "
            "(missing 'summary'/'runs')."
        )
    return data


def _mode_stats_from_runs(runs: list[dict[str, Any]], mode: str) -> dict[str, Any] | None:
    mode_runs = [run for run in runs if run.get("mode") == mode]
    if not mode_runs:
        return None
    episodes = len(mode_runs)
    successes = sum(1 for run in mode_runs if run.get("success"))
    token_total = sum(int(run.get("decision_tokens") or 0) for run in mode_runs)
    return {
        "mode": mode,
        "episodes": episodes,
        "successes": successes,
        "success_rate": successes / episodes,
        "decision_tokens": token_total,
        "avg_decision_tokens": token_total / episodes,
    }


def per_mode_stats(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return ``{mode: stats}`` for a single report.

    Prefers the producer's ``summary.by_mode`` rows and falls back to
    recomputing from ``runs`` so partial reports still summarize.
    """

    stats: dict[str, dict[str, Any]] = {}
    summary = report.get("summary") or {}
    for row in summary.get("by_mode") or []:
        mode = row.get("mode")
        if not mode:
            continue
        episodes = int(row.get("episodes") or 0)
        if episodes <= 0:
            continue
        successes = int(row.get("successes") or 0)
        token_total = int(row.get("decision_tokens") or 0)
        stats[mode] = {
            "mode": mode,
            "episodes": episodes,
            "successes": successes,
            "success_rate": float(
                row.get("success_rate", successes / episodes)
            ),
            "decision_tokens": token_total,
            "avg_decision_tokens": float(
                row.get("avg_decision_tokens", token_total / episodes)
            ),
        }
    if not stats:
        runs = report.get("runs") or []
        modes = report.get("modes") or sorted({run.get("mode") for run in runs if run.get("mode")})
        for mode in modes:
            row = _mode_stats_from_runs(runs, mode)
            if row is not None:
                stats[mode] = row
    return stats


def failure_class_counts(report: dict[str, Any]) -> dict[str, int]:
    summary = report.get("summary") or {}
    classes = summary.get("failure_classes")
    if isinstance(classes, dict) and classes:
        return {str(name): int(count) for name, count in classes.items()}
    counts: dict[str, int] = {}
    for row in report.get("failure_table") or []:
        name = str(row.get("failure_class") or "unknown")
        counts[name] = counts.get(name, 0) + 1
    return counts


def _ordered_modes(per_report: list[dict[str, dict[str, Any]]]) -> list[str]:
    modes: list[str] = []
    for stats in per_report:
        for mode in stats:
            if mode not in modes:
                modes.append(mode)
    if COMPACT_MODE in modes:
        modes = [COMPACT_MODE] + [mode for mode in modes if mode != COMPACT_MODE]
    return modes


def _aggregate_metric(values: list[float]) -> dict[str, Any]:
    n = len(values)
    mean = statistics.fmean(values) if values else 0.0
    std = statistics.stdev(values) if n > 1 else 0.0
    sem = std / (n ** 0.5) if n > 1 else 0.0
    return {
        "mean": mean,
        "std": std,
        "sem": sem,
        "n": n,
        "values": values,
    }


def build_summary(name: str, report_paths: list[Path]) -> dict[str, Any]:
    reports = [load_report(path) for path in report_paths]
    per_report = [per_mode_stats(report) for report in reports]
    modes = _ordered_modes(per_report)
    baseline_mode = next((mode for mode in modes if mode != COMPACT_MODE), None)

    success_rate: dict[str, Any] = {}
    avg_tokens: dict[str, Any] = {}
    for mode in modes:
        rates = [stats[mode]["success_rate"] for stats in per_report if mode in stats]
        tokens = [stats[mode]["avg_decision_tokens"] for stats in per_report if mode in stats]
        successes_total = sum(stats[mode]["successes"] for stats in per_report if mode in stats)
        episodes_total = sum(stats[mode]["episodes"] for stats in per_report if mode in stats)
        rate_agg = _aggregate_metric(rates)
        rate_agg["successes_total"] = successes_total
        rate_agg["episodes_total"] = episodes_total
        success_rate[mode] = rate_agg
        token_agg = _aggregate_metric(tokens)
        token_agg["total"] = sum(
            stats[mode]["decision_tokens"] for stats in per_report if mode in stats
        )
        avg_tokens[mode] = token_agg

    failure_classes: dict[str, int] = {}
    for report in reports:
        for cls, count in failure_class_counts(report).items():
            failure_classes[cls] = failure_classes.get(cls, 0) + count
    failure_classes = dict(sorted(failure_classes.items()))

    compact_only_wins = failure_classes.get("compact_only_success", 0)
    compact_regressions = failure_classes.get("compact_regression", 0)

    return {
        "name": name,
        "report_count": len(reports),
        "reports": [
            {
                "path": str(path),
                "suite": report.get("suite"),
                "suite_kind": report.get("suite_kind"),
                "source": report.get("source"),
                "modes": report.get("modes"),
                "episodes": (report.get("summary") or {}).get("episodes"),
            }
            for path, report in zip(report_paths, reports)
        ],
        "modes": modes,
        "baseline_mode": baseline_mode,
        "multi_seed": len(reports) > 1,
        "success_rate": success_rate,
        "avg_tokens": avg_tokens,
        "failure_classes": failure_classes,
        "compact_only_wins": compact_only_wins,
        "compact_regressions": compact_regressions,
    }


def _bar_colors(modes: list[str]) -> list[str]:
    palette = {
        "compact": "#2563eb",
        "full_state": "#9ca3af",
        "vision_full_state": "#f97316",
    }
    return [palette.get(mode, "#6b7280") for mode in modes]


def _save(fig: "plt.Figure", path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=144)
    plt.close(fig)


def chart_success_rate(summary: dict[str, Any], path: Path) -> None:
    modes = summary["modes"]
    means = [summary["success_rate"][mode]["mean"] * 100 for mode in modes]
    errors = [summary["success_rate"][mode]["std"] * 100 for mode in modes]
    has_errors = summary["multi_seed"] and any(e > 0 for e in errors)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(
        modes,
        means,
        yerr=errors if has_errors else None,
        capsize=8 if has_errors else 0,
        color=_bar_colors(modes),
    )
    for idx, mean in enumerate(means):
        ax.text(idx, mean, f"{mean:.1f}%", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("Success rate (%)")
    ax.set_ylim(0, 105)
    title = "Success rate by observation mode"
    if has_errors:
        title += f" (mean ± std over {summary['report_count']} seeds)"
    ax.set_title(title)
    _save(fig, path)


def chart_avg_tokens(summary: dict[str, Any], path: Path) -> None:
    modes = summary["modes"]
    means = [summary["avg_tokens"][mode]["mean"] for mode in modes]
    errors = [summary["avg_tokens"][mode]["std"] for mode in modes]
    has_errors = summary["multi_seed"] and any(e > 0 for e in errors)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(
        modes,
        means,
        yerr=errors if has_errors else None,
        capsize=8 if has_errors else 0,
        color=_bar_colors(modes),
    )
    for idx, mean in enumerate(means):
        ax.text(idx, mean, f"{mean:.0f}", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("Avg decision tokens per episode")
    title = "Average token usage by observation mode"
    if has_errors:
        title += f" (mean ± std over {summary['report_count']} seeds)"
    ax.set_title(title)
    _save(fig, path)


def chart_failure_classes(summary: dict[str, Any], path: Path) -> None:
    classes = summary["failure_classes"]
    labels = list(classes.keys()) or ["(none)"]
    counts = list(classes.values()) or [0]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(labels, counts, color="#6366f1")
    for idx, count in enumerate(counts):
        ax.text(idx, count, str(count), ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("Episode count")
    ax.set_title("Failure class breakdown")
    ax.tick_params(axis="x", labelrotation=30)
    for label in ax.get_xticklabels():
        label.set_ha("right")
    _save(fig, path)


def chart_compact_outcomes(summary: dict[str, Any], path: Path) -> None:
    labels = ["compact-only wins", "compact regressions"]
    counts = [summary["compact_only_wins"], summary["compact_regressions"]]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(labels, counts, color=["#16a34a", "#dc2626"])
    for idx, count in enumerate(counts):
        ax.text(idx, count, str(count), ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("Episode count")
    ax.set_title("Compact-only wins vs compact regressions")
    _save(fig, path)


CHART_BUILDERS = {
    "success_rate.png": chart_success_rate,
    "avg_tokens.png": chart_avg_tokens,
    "failure_classes.png": chart_failure_classes,
    "compact_outcomes.png": chart_compact_outcomes,
}


def render_charts(summary: dict[str, Any], out_dir: Path) -> list[str]:
    written: list[str] = []
    for filename, builder in CHART_BUILDERS.items():
        builder(summary, out_dir / filename)
        written.append(filename)
    return written


def _fmt_metric(agg: dict[str, Any], *, pct: bool, digits: int) -> str:
    scale = 100 if pct else 1
    mean = agg["mean"] * scale
    suffix = "%" if pct else ""
    text = f"{mean:.{digits}f}{suffix}"
    if agg["n"] > 1 and agg["std"] > 0:
        text += f" ± {agg['std'] * scale:.{digits}f}{suffix}"
    return text


def render_markdown(summary: dict[str, Any], chart_files: list[str]) -> str:
    modes = summary["modes"]
    lines = [
        f"# {summary['name']}",
        "",
        f"- Reports summarized: {summary['report_count']}"
        + (" (multi-seed, error bars shown)" if summary["multi_seed"] else ""),
        f"- Modes: {', '.join(modes)}",
        f"- Baseline mode: {summary['baseline_mode'] or 'n/a'}",
        f"- Compact-only wins: {summary['compact_only_wins']}",
        f"- Compact regressions: {summary['compact_regressions']}",
        "",
        "## Success rate and token usage",
        "",
        "| Mode | Success rate | Successes | Avg tokens |",
        "| --- | --- | --- | --- |",
    ]
    for mode in modes:
        rate = summary["success_rate"][mode]
        tokens = summary["avg_tokens"][mode]
        lines.append(
            "| "
            + " | ".join(
                [
                    mode,
                    _fmt_metric(rate, pct=True, digits=1),
                    f"{rate['successes_total']}/{rate['episodes_total']}",
                    _fmt_metric(tokens, pct=False, digits=0),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Failure class breakdown", "", "| Class | Episodes |", "| --- | --- |"])
    if summary["failure_classes"]:
        for cls, count in summary["failure_classes"].items():
            lines.append(f"| {cls} | {count} |")
    else:
        lines.append("| (none) | 0 |")

    lines.extend(["", "## Charts", ""])
    for filename in chart_files:
        title = filename.replace(".png", "").replace("_", " ").title()
        lines.append(f"### {title}")
        lines.append("")
        lines.append(f"![{title}]({filename})")
        lines.append("")

    lines.extend(["## Source reports", ""])
    for entry in summary["reports"]:
        suite = entry.get("suite") or "?"
        lines.append(f"- `{entry['path']}` (suite: {suite})")
    return "\n".join(lines).rstrip() + "\n"


def summarize(
    report_paths: list[Path],
    out_dir: Path,
    name: str | None = None,
) -> dict[str, Any]:
    if not report_paths:
        raise ReportError("At least one report path is required.")
    first = load_report(report_paths[0])
    resolved_name = name or _slugify(str(first.get("suite") or report_paths[0].stem))
    summary = build_summary(resolved_name, report_paths)

    target = out_dir / resolved_name
    target.mkdir(parents=True, exist_ok=True)
    chart_files = render_charts(summary, target)
    summary["charts"] = chart_files

    (target / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (target / "summary.md").write_text(render_markdown(summary, chart_files))
    summary["output_dir"] = str(target)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "reports",
        nargs="+",
        type=Path,
        help="One or more run_browsergym_live.py JSON reports.",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Output folder name under the out-dir. Defaults to the suite slug.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Parent directory for the generated report folder.",
    )
    args = parser.parse_args(argv)

    try:
        summary = summarize(args.reports, args.out_dir, name=args.name)
    except ReportError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    out_dir = summary["output_dir"]
    print(f"wrote {out_dir}/summary.json")
    print(f"wrote {out_dir}/summary.md")
    for filename in summary["charts"]:
        print(f"wrote {out_dir}/{filename}")
    for mode in summary["modes"]:
        rate = summary["success_rate"][mode]
        tokens = summary["avg_tokens"][mode]
        print(
            f"{mode}: success={rate['mean'] * 100:.1f}% "
            f"avg_tokens={tokens['mean']:.0f}"
        )
    print(
        f"compact_only_wins={summary['compact_only_wins']} "
        f"compact_regressions={summary['compact_regressions']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
