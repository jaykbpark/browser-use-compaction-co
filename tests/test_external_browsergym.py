from __future__ import annotations

import builtins
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from browserdelta.config import get_settings
from browserdelta.eval.runner import evaluate_run
from browserdelta.external import browsergym_adapter as bg
from browserdelta.external import browsergym_live as bgl
from browserdelta.schemas import (
    EvalComparisonReport,
    EvalComparisonSummary,
    ReplayReport,
)


def _node(
    node_id: str,
    role: str,
    name: str,
    bid: str | None = None,
    value: str | None = None,
    props: dict[str, object] | None = None,
) -> dict:
    node = {"nodeId": node_id, "role": {"value": role}, "name": {"value": name}}
    if bid is not None:
        node["browsergym_id"] = bid
    if value is not None:
        node["value"] = {"value": value}
    if props:
        node["properties"] = [
            {"name": key, "value": {"value": value}} for key, value in props.items()
        ]
    return node


def _obs(step: int) -> dict:
    screenshot = np.zeros((48, 64, 3), dtype=np.uint8)
    screenshot[step * 5 : step * 5 + 8, :, :] = 255
    return {
        "url": f"about:miniwob/step{step}",
        "goal": "Click the button labeled ONE.",
        "open_pages_titles": ("MiniWoB Task",),
        "active_page_index": [0],
        "screenshot": screenshot,
        "axtree_object": {
            "nodes": [
                _node("1", "RootWebArea", "MiniWoB Task"),
                _node("2", "button", "Start", bid="a0"),
                _node("3", "button", "ONE", bid="a1", props={"disabled": step >= 2}),
                _node("4", "textbox", "Name", bid="a2", value=f"value-{step}"),
                _node("5", "StaticText", "decoration"),
            ]
        },
        "extra_element_properties": {"a1": {"bbox": [10, 20, 30, 12], "clickable": True}},
        "focused_element_bid": "a2",
        "last_action": "click('a1')" if step else None,
        "last_action_error": "",
    }


class _FakeEnv:
    def __init__(self, observations: list[dict]):
        self.observations = observations
        self.index = 0
        self.closed = False

    def reset(self):
        self.index = 0
        return self.observations[0], {}

    def step(self, _action: str):
        self.index += 1
        done = self.index >= len(self.observations) - 1
        return self.observations[self.index], float(done), done, False, {"success": done}

    def close(self):
        self.closed = True


class _FakeGym:
    def __init__(self, env: _FakeEnv):
        self.env = env

    def make(self, _env_id: str, **_kwargs):
        return self.env


def test_observation_to_page_state_from_mock_browsergym_obs():
    state = bg.observation_to_page_state(_obs(0), screenshot="steps/x.png")

    assert state.url == "about:miniwob/step0"
    assert state.title == "MiniWoB Task"
    assert state.metadata["goal"] == "Click the button labeled ONE."
    assert state.focused_ref == "a2"
    refs = {item.ref: item for item in state.interactive}
    assert set(refs) == {"a0", "a1", "a2"}
    assert refs["a1"].bbox is not None
    assert refs["a1"].bbox.width == 30
    assert refs["a2"].value == "value-0"
    assert "ONE" in state.text


def test_parse_browsergym_action_handles_quoted_commas():
    fill = bg.parse_browsergym_action("fill('a2', 'hello, world')")
    assert fill.type == "type"
    assert fill.target == "a2"
    assert fill.text == "hello, world"

    press = bg.parse_browsergym_action("press('a2', 'Enter')")
    assert press.type == "press"
    assert press.key == "Enter"
    assert bg.parse_browsergym_action("noop()").type == "wait"


def test_format_browsergym_action_outputs_browsergym_calls():
    assert bg.format_browsergym_action(bg.parse_browsergym_action("click('a1')")) == "click('a1')"
    assert (
        bg.format_browsergym_action(bg.parse_browsergym_action("fill('a2', 'hello, world')"))
        == "fill('a2', 'hello, world')"
    )
    assert bg.format_browsergym_action(bg.parse_browsergym_action("noop()")) == "noop()"


def test_record_episode_with_fake_env_writes_browserdelta_run(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))
    get_settings.cache_clear()
    env = _FakeEnv([_obs(index) for index in range(4)])

    run_path = bg.record_episode(
        "browsergym/miniwob.click-button",
        "bg_fake",
        gym_module=_FakeGym(env),
        actions=["click('a0')", "click('a1')", "click('a1')"],
        compact=True,
    )

    assert env.closed
    assert (run_path / "run.json").is_file()
    assert (run_path / "steps.jsonl").is_file()
    assert (run_path / "compact_observations.jsonl").is_file()
    manifest = json.loads((run_path / "run.json").read_text())
    assert manifest["metadata"]["source"] == "browsergym"
    assert manifest["metadata"]["policy"] == "scripted"
    assert manifest["metadata"]["success"] is True

    report = evaluate_run(run_path, predictor="heuristic")
    assert report.evaluated_steps >= 2
    assert report.compact_tokens > 0

    get_settings.cache_clear()


def test_run_live_episode_records_compact_agent_trace(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))
    get_settings.cache_clear()
    env = _FakeEnv([_obs(index) for index in range(3)])

    result = bgl.run_live_episode(
        "browsergym/miniwob.click-button",
        "live_fake_compact",
        mode="compact",
        policy=bgl.ScriptedBrowserGymPolicy(["click('a0')", "click('a1')"]),
        gym_module=_FakeGym(env),
        max_steps=3,
    )

    run_path = Path(result["run_path"])
    assert result["success"] is True
    assert result["mode"] == "compact"
    assert result["decision_tokens"] > 0
    assert result["baseline_tokens"] >= result["decision_tokens"]
    assert (run_path / "steps.jsonl").is_file()
    assert (run_path / "compact_observations.jsonl").is_file()
    assert result["decisions"][0]["browsergym_action"] == "click('a0')"

    get_settings.cache_clear()


def test_run_live_suite_builds_failure_table_and_chart_payload(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))
    get_settings.cache_clear()
    env = _FakeEnv([_obs(index) for index in range(3)])

    report = bgl.run_live_suite(
        {
            "suite": "fake-live",
            "episodes": [
                {
                    "env_id": "browsergym/miniwob.click-button",
                    "run_id": "fake_live",
                    "actions": ["click('a0')", "click('a1')"],
                }
            ],
        },
        modes=["compact", "full_state"],
        gym_module=_FakeGym(env),
        max_steps=3,
    )

    assert report["summary"]["episodes"] == 1
    assert report["failure_table"][0]["failure_class"] == "both_success"
    assert report["failure_table"][0]["compact_success"] is True
    assert report["charts"]["success_by_mode"][0]["episodes"] == 1
    assert {row["mode"] for row in report["summary"]["by_mode"]} == {"compact", "full_state"}

    get_settings.cache_clear()


def test_probe_workarena_gracefully_reports_missing_registry():
    class EmptyGym:
        class envs:
            registry: dict[str, object] = {}

    probe = bgl.probe_workarena(gym_module=EmptyGym())

    assert probe["available"] is False
    assert probe["env_count"] == 0
    assert "WorkArena" in probe["message"]


def test_require_browsergym_has_helpful_isolated_env_error(monkeypatch):
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "gymnasium" or name.startswith("browsergym"):
            raise ImportError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(bg.BrowserGymUnavailable) as exc:
        bg.require_browsergym()

    message = str(exc.value)
    assert "isolated BrowserGym environment" in message
    assert "Playwright 1.44" in message


def test_eval_external_suite_uses_existing_comparison_summary(tmp_path: Path, monkeypatch):
    script = _load_script("eval_external_suite")
    run_path = tmp_path / "runs" / "bg_fake"
    calls: list[tuple[str, str, list[str]]] = []

    def fake_record_episode(env_id, run_id, *, actions=None, **_kwargs):
        calls.append((env_id, run_id, list(actions or [])))
        run_path.mkdir(parents=True, exist_ok=True)
        return run_path

    def fake_evaluate_comparison(path, **_kwargs):
        compact = ReplayReport(
            run_id=path.name,
            predictor="heuristic",
            context_mode="compact",
            evaluated_steps=2,
            passed_steps=2,
            next_action_accuracy=1.0,
            compact_tokens=40,
            baseline_tokens=100,
            avg_reduction_pct=60,
        )
        baseline = ReplayReport(
            run_id=path.name,
            predictor="heuristic",
            context_mode="vision_full_state",
            evaluated_steps=2,
            passed_steps=2,
            next_action_accuracy=1.0,
            compact_tokens=100,
            baseline_tokens=100,
            avg_reduction_pct=0,
        )
        summary = EvalComparisonSummary(
            run_id=path.name,
            predictor="heuristic",
            baseline_context_mode="vision_full_state",
            evaluated_steps=2,
            compact_passed_steps=2,
            baseline_passed_steps=2,
            compact_accuracy=1.0,
            baseline_accuracy=1.0,
            accuracy_delta=0,
            compact_tokens=40,
            baseline_tokens=100,
            token_savings=60,
            token_reduction_pct=60,
        )
        return EvalComparisonReport(
            run_id=path.name,
            predictor="heuristic",
            compact=compact,
            baseline=baseline,
            summary=summary,
            verdict="compact_matches_or_beats_baseline",
        )

    monkeypatch.setattr(script, "record_episode", fake_record_episode)
    monkeypatch.setattr(script, "evaluate_comparison", fake_evaluate_comparison)

    report = script.run_external_suite(
        {
            "suite": "browsergym-miniwob-smoke",
            "episodes": [
                {
                    "env_id": "browsergym/miniwob.click-button",
                    "run_id": "bg_fake",
                    "actions": ["click('a0')"],
                }
            ],
        },
        compare=True,
    )

    assert calls == [("browsergym/miniwob.click-button", "bg_fake", ["click('a0')"])]
    assert report["summary"]["compact_passed_evaluated"] == "2/2"
    assert report["summary"]["token_reduction_pct"] == 60


def _load_script(name: str):
    repo_root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(name, repo_root / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
