from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def test_build_failure_suite_defaults_to_hard_failures():
    script = _load_script("build_failure_suite")

    suite = script.build_failure_suite(_report(), source_report="report.json")

    assert suite["suite"] == "miniwob-50-failure-loop"
    assert suite["source_report"] == "report.json"
    assert suite["selected_failure_classes"] == ["compact_regression", "both_failed"]
    assert [episode["env_id"] for episode in suite["episodes"]] == [
        "browsergym/miniwob.click-checkboxes-large",
        "browsergym/miniwob.daily-calendar",
    ]
    assert suite["episodes"][0]["run_id"] == "failure_loop_miniwob_click_checkboxes_large"
    assert suite["episodes"][0]["goal"] == "Click every requested checkbox."
    assert suite["episodes"][0]["max_steps"] == 10
    assert suite["episodes"][0]["metadata"]["source_failure_class"] == "compact_regression"


def test_build_failure_suite_can_include_compact_wins_and_limit():
    script = _load_script("build_failure_suite")

    suite = script.build_failure_suite(
        _report(),
        failure_classes=list(script.NON_SUCCESS_CLASSES),
        limit=2,
        run_prefix="rerun",
    )

    assert [episode["run_id"] for episode in suite["episodes"]] == [
        "rerun_miniwob_click_checkboxes_large",
        "rerun_miniwob_daily_calendar",
    ]
    assert len(suite["episodes"]) == 2


def test_failure_suite_cli_writes_json(tmp_path: Path, capsys):
    script = _load_script("build_failure_suite")
    report_path = tmp_path / "report.json"
    out_path = tmp_path / "failure-suite.json"
    report_path.write_text(json.dumps(_report()))

    assert script.main([str(report_path), "--all-non-success", "--out", str(out_path)]) == 0

    captured = capsys.readouterr()
    assert "wrote" in captured.out
    suite = json.loads(out_path.read_text())
    assert [episode["env_id"] for episode in suite["episodes"]] == [
        "browsergym/miniwob.click-checkboxes-large",
        "browsergym/miniwob.daily-calendar",
        "browsergym/miniwob.click-test",
    ]


def _report() -> dict:
    return {
        "suite": "miniwob-50",
        "summary": {
            "episodes": 4,
            "failure_classes": {
                "both_success": 1,
                "compact_regression": 1,
                "both_failed": 1,
                "compact_only_success": 1,
            },
        },
        "runs": [
            {
                "run_id": "large_compact",
                "env_id": "browsergym/miniwob.click-checkboxes-large",
                "goal": "Click every requested checkbox.",
                "steps": 8,
            },
            {
                "run_id": "calendar_compact",
                "env_id": "browsergym/miniwob.daily-calendar",
                "goal": "Create the requested calendar event.",
                "steps": 10,
            },
            {
                "run_id": "click_test_compact",
                "env_id": "browsergym/miniwob.click-test",
                "goal": "Click the requested test target.",
                "steps": 2,
            },
        ],
        "failure_table": [
            {
                "env_id": "browsergym/miniwob.click-button",
                "compact_run_id": "button_compact",
                "baseline_run_id": "button_full",
                "compact_success": True,
                "baseline_success": True,
                "compact_steps": 1,
                "baseline_steps": 1,
                "token_reduction_pct": 90.0,
                "failure_class": "both_success",
            },
            {
                "env_id": "browsergym/miniwob.click-checkboxes-large",
                "compact_run_id": "large_compact",
                "baseline_run_id": "large_full",
                "compact_success": False,
                "baseline_success": True,
                "compact_steps": 10,
                "baseline_steps": 9,
                "token_reduction_pct": 85.5,
                "failure_class": "compact_regression",
            },
            {
                "env_id": "browsergym/miniwob.daily-calendar",
                "compact_run_id": "calendar_compact",
                "baseline_run_id": "calendar_full",
                "compact_success": False,
                "baseline_success": False,
                "compact_steps": 10,
                "baseline_steps": 10,
                "token_reduction_pct": 86.2,
                "failure_class": "both_failed",
            },
            {
                "env_id": "browsergym/miniwob.click-test",
                "compact_run_id": "click_test_compact",
                "baseline_run_id": "click_test_full",
                "compact_success": True,
                "baseline_success": False,
                "compact_steps": 2,
                "baseline_steps": 10,
                "token_reduction_pct": 96.4,
                "failure_class": "compact_only_success",
            },
        ],
    }


def _load_script(name: str):
    repo_root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(name, repo_root / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
