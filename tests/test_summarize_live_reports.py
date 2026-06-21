from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "summarize_live_reports", repo_root / "scripts" / "summarize_live_reports.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


summarize_live_reports = _load_module()


def _fake_report(
    *,
    suite: str = "fake-suite",
    compact_successes: int,
    full_successes: int,
    episodes: int,
    compact_avg_tokens: float,
    full_avg_tokens: float,
    failure_classes: dict[str, int],
) -> dict[str, Any]:
    """Tiny synthetic run_browsergym_live.py report. No real raw reports used."""

    return {
        "schema_version": 1,
        "suite": suite,
        "source": "browsergym-live",
        "suite_kind": "miniwob",
        "modes": ["compact", "full_state"],
        "runs": [],
        "failure_table": [],
        "summary": {
            "episodes": episodes,
            "by_mode": [
                {
                    "mode": "compact",
                    "episodes": episodes,
                    "successes": compact_successes,
                    "success_rate": compact_successes / episodes,
                    "decision_tokens": int(compact_avg_tokens * episodes),
                    "avg_decision_tokens": compact_avg_tokens,
                    "avg_steps": 1.0,
                },
                {
                    "mode": "full_state",
                    "episodes": episodes,
                    "successes": full_successes,
                    "success_rate": full_successes / episodes,
                    "decision_tokens": int(full_avg_tokens * episodes),
                    "avg_decision_tokens": full_avg_tokens,
                    "avg_steps": 1.0,
                },
            ],
            "failure_classes": dict(failure_classes),
            "compact_regressions": failure_classes.get("compact_regression", 0),
        },
    }


def _write(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload, indent=2))
    return path


def test_single_report_summary_has_no_error_bars(tmp_path: Path):
    report = _fake_report(
        compact_successes=2,
        full_successes=1,
        episodes=2,
        compact_avg_tokens=20.0,
        full_avg_tokens=200.0,
        failure_classes={"both_success": 1, "compact_only_success": 1},
    )
    report_path = _write(tmp_path / "seed1.json", report)

    summary = summarize_live_reports.summarize([report_path], tmp_path / "out")

    assert summary["report_count"] == 1
    assert summary["multi_seed"] is False
    assert summary["modes"] == ["compact", "full_state"]
    assert summary["baseline_mode"] == "full_state"
    assert summary["success_rate"]["compact"]["mean"] == 1.0
    assert summary["success_rate"]["compact"]["std"] == 0.0
    assert summary["success_rate"]["full_state"]["mean"] == 0.5
    assert summary["avg_tokens"]["compact"]["mean"] == 20.0
    assert summary["avg_tokens"]["full_state"]["mean"] == 200.0
    assert summary["compact_only_wins"] == 1
    assert summary["compact_regressions"] == 0

    out_dir = Path(summary["output_dir"])
    assert (out_dir / "summary.json").exists()
    assert (out_dir / "summary.md").exists()
    for chart in summarize_live_reports.CHART_BUILDERS:
        assert (out_dir / chart).exists()
        assert (out_dir / chart).stat().st_size > 0


def test_multi_seed_reports_produce_error_bars(tmp_path: Path):
    seed1 = _write(
        tmp_path / "seed1.json",
        _fake_report(
            compact_successes=2,
            full_successes=2,
            episodes=2,
            compact_avg_tokens=20.0,
            full_avg_tokens=200.0,
            failure_classes={"both_success": 2},
        ),
    )
    seed2 = _write(
        tmp_path / "seed2.json",
        _fake_report(
            compact_successes=1,
            full_successes=2,
            episodes=2,
            compact_avg_tokens=30.0,
            full_avg_tokens=220.0,
            failure_classes={"both_success": 1, "compact_regression": 1},
        ),
    )

    summary = summarize_live_reports.summarize([seed1, seed2], tmp_path / "out", name="demo")

    assert summary["report_count"] == 2
    assert summary["multi_seed"] is True
    # compact rates across seeds: 1.0 and 0.5 -> mean 0.75, std > 0
    assert summary["success_rate"]["compact"]["mean"] == 0.75
    assert summary["success_rate"]["compact"]["std"] > 0
    assert summary["success_rate"]["compact"]["n"] == 2
    # full_state perfect across both seeds -> no spread
    assert summary["success_rate"]["full_state"]["mean"] == 1.0
    assert summary["success_rate"]["full_state"]["std"] == 0.0
    # failure classes aggregated across seeds
    assert summary["failure_classes"]["both_success"] == 3
    assert summary["compact_regressions"] == 1
    assert summary["compact_only_wins"] == 0

    out_dir = Path(summary["output_dir"])
    assert out_dir.name == "demo"
    written = json.loads((out_dir / "summary.json").read_text())
    assert written["multi_seed"] is True


def test_fallback_to_runs_when_summary_missing(tmp_path: Path):
    report = {
        "suite": "runs-only",
        "modes": ["compact", "full_state"],
        "runs": [
            {"mode": "compact", "success": True, "decision_tokens": 10},
            {"mode": "compact", "success": False, "decision_tokens": 14},
            {"mode": "full_state", "success": True, "decision_tokens": 300},
            {"mode": "full_state", "success": True, "decision_tokens": 320},
        ],
        "failure_table": [
            {"failure_class": "compact_regression"},
            {"failure_class": "both_success"},
        ],
    }
    report_path = _write(tmp_path / "runs_only.json", report)

    summary = summarize_live_reports.summarize([report_path], tmp_path / "out")

    assert summary["success_rate"]["compact"]["mean"] == 0.5
    assert summary["avg_tokens"]["compact"]["mean"] == 12.0
    assert summary["success_rate"]["full_state"]["mean"] == 1.0
    assert summary["failure_classes"]["compact_regression"] == 1
    assert summary["compact_regressions"] == 1


def test_rejects_non_report_json(tmp_path: Path):
    bad = _write(tmp_path / "bad.json", {"hello": "world"})
    try:
        summarize_live_reports.summarize([bad], tmp_path / "out")
    except summarize_live_reports.ReportError:
        pass
    else:
        raise AssertionError("expected ReportError for non-report JSON")


def test_cli_writes_outputs(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    report = _fake_report(
        compact_successes=2,
        full_successes=1,
        episodes=2,
        compact_avg_tokens=18.0,
        full_avg_tokens=210.0,
        failure_classes={"both_success": 1, "compact_only_success": 1},
    )
    report_path = _write(tmp_path / "seed1.json", report)
    out_dir = tmp_path / "reports" / "demo"

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "summarize_live_reports.py"),
            str(report_path),
            "--name",
            "cli-demo",
            "--out-dir",
            str(out_dir),
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
    )

    target = out_dir / "cli-demo"
    assert (target / "summary.json").exists()
    assert (target / "summary.md").exists()
    assert (target / "success_rate.png").exists()
    assert "compact_only_wins=1" in result.stdout
