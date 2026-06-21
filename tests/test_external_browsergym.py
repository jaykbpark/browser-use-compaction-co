"""Tests for the external BrowserGym/MiniWoB eval path.

None of these require BrowserGym to be installed: observation conversion and
report aggregation are dependency-free, recording uses a fake env, the missing
-dependency path is forced, and the LLM predictor is monkeypatched.
"""

from __future__ import annotations

import sys

import numpy as np
import pytest

from browserdelta.eval.ab import evaluate_run
from browserdelta.external import browsergym_adapter as bg
from browserdelta.external.suite import aggregate_suite_report


def _node(node_id, role, name, bid=None, value=None, props=None):
    node = {
        "nodeId": node_id,
        "role": {"value": role},
        "name": {"value": name},
    }
    if bid is not None:
        node["browsergym_id"] = bid
    if value is not None:
        node["value"] = {"value": value}
    if props:
        node["properties"] = [{"name": k, "value": {"value": v}} for k, v in props.items()]
    return node


def _obs(step_idx):
    axtree = {
        "nodes": [
            _node("1", "RootWebArea", "MiniWoB Task"),
            _node("2", "button", "Start", bid="a0"),
            _node("3", "button", "ONE", bid="a1", props={"disabled": step_idx >= 2}),
            _node("4", "textbox", "Name", bid="a2", value=f"v{step_idx}"),
            _node("5", "StaticText", "decoration"),
        ]
    }
    shot = np.zeros((48, 64, 3), dtype=np.uint8)
    shot[step_idx * 5 : step_idx * 5 + 8, :, :] = 255  # vary so diffs are nonzero
    return {
        "url": f"about:miniwob/step{step_idx}",
        "goal": "Click the button labeled ONE.",
        "goal_object": ({"type": "text", "text": "Click the button labeled ONE."},),
        "open_pages_titles": ("MiniWoB Task",),
        "active_page_index": [0],
        "screenshot": shot,
        "axtree_object": axtree,
        "extra_element_properties": {"a1": {"bbox": [10, 20, 30, 12], "clickable": True}},
        "focused_element_bid": "a2",
        "last_action": "click('a1')" if step_idx else None,
        "last_action_error": "",
    }


class _FakeEnv:
    def __init__(self, observations):
        self._observations = observations
        self._i = 0

    def reset(self):
        self._i = 0
        return self._observations[0], {}

    def step(self, _action):
        self._i += 1
        obs = self._observations[self._i]
        done = self._i >= len(self._observations) - 1
        reward = 1.0 if done else 0.0
        return obs, reward, done, False, {"success": done}

    def close(self):
        pass


class _FakeGym:
    def __init__(self, env):
        self._env = env

    def make(self, _env_id, **_kwargs):
        return self._env


def test_observation_to_page_state_from_mock_obs():
    state = bg.observation_to_page_state(_obs(0), screenshot="steps/x.png")

    assert state.url == "about:miniwob/step0"
    assert state.title == "MiniWoB Task"
    assert state.metadata["goal"] == "Click the button labeled ONE."
    assert state.focused_ref == "a2"
    refs = {e.ref: e for e in state.interactive}
    assert set(refs) == {"a0", "a1", "a2"}  # only elements with a bid
    assert refs["a1"].name == "ONE"
    assert refs["a1"].bbox is not None and refs["a1"].bbox.width == 30
    assert refs["a2"].value == "v0"
    assert "decoration" in state.text and "ONE" in state.text


def test_parse_action_maps_browsergym_verbs():
    assert bg.parse_action("click('a1')").type == "click"
    assert bg.parse_action("click('a1')").target == "a1"
    fill = bg.parse_action("fill('a2', 'hello world')")
    assert fill.type == "type" and fill.target == "a2" and fill.text == "hello world"
    assert bg.parse_action("press('a2', 'Enter')").key == "Enter"
    assert bg.parse_action("noop()").type == "wait"
    assert bg.parse_action(None).type == "wait"


def test_records_and_compacts_with_fake_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    gym = _FakeGym(_FakeEnv([_obs(i) for i in range(4)]))

    run_path = bg.record_episode(
        "browsergym/miniwob.click-button",
        "bg_fake",
        max_steps=10,
        gym_module=gym,
        compact=True,
    )

    assert (run_path / "steps.jsonl").exists()
    compact = run_path / "compact_observations.jsonl"
    assert compact.exists()
    rows = [line for line in compact.read_text().splitlines() if line.strip()]
    assert len(rows) >= 3

    import json

    manifest = json.loads((run_path / "run.json").read_text())
    assert manifest["metadata"]["source"] == "browsergym"
    assert manifest["metadata"]["success"] is True
    # at least one observation carries a route/summary
    assert any("summary" in json.loads(r) and json.loads(r).get("fallback") for r in rows)


def test_evaluate_run_heuristic_on_recorded_episode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    gym = _FakeGym(_FakeEnv([_obs(i) for i in range(4)]))
    run_path = bg.record_episode("env", "bg_h", gym_module=gym, compact=True)

    report = evaluate_run(run_path, predictor="heuristic")
    assert report["summary"]["n_steps"] >= 3
    assert report["summary"]["tokens"]["compact_total"] > 0


def test_evaluate_run_llm_predictor_is_mocked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    gym = _FakeGym(_FakeEnv([_obs(i) for i in range(4)]))
    run_path = bg.record_episode("env", "bg_llm", gym_module=gym, compact=True)

    calls = {"n": 0}

    def fake_choose(goal, target_hint, candidates, model="gpt-4o-mini"):
        calls["n"] += 1
        for el in candidates:
            if el.name.lower() == "one":
                return el.ref
        return None

    monkeypatch.setattr("browserdelta.eval.ab.llm_choose_element", fake_choose)

    task = {
        "id": "bg_llm",
        "goal": "Click the button labeled ONE.",
        "actions": [
            {"type": "click", "target": "Start"},
            {"type": "click", "target": "ONE"},
            {"type": "click", "target": "ONE"},
        ],
    }
    report = evaluate_run(run_path, task=task, predictor="llm")
    assert calls["n"] > 0  # the LLM path ran, mocked (no real API call)
    assert report["summary"]["next_action"]["compact_accuracy"] is not None


def test_missing_browsergym_raises_helpful_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "browsergym.core", None)
    with pytest.raises(bg.BrowserGymUnavailable) as exc:
        bg.require_browsergym()
    assert "external-evals" in str(exc.value)


def test_aggregate_suite_report():
    per_run = [
        {
            "env_id": "browsergym/miniwob.click-button",
            "run_id": "a",
            "n_steps": 3,
            "success": True,
            "reward": 1.0,
            "latency_s": 0.5,
            "tokens": {"vision_full_state": 1000, "full_state": 300, "compact": 120},
            "next_action": {"vision_full_state": 1.0, "full_state": 1.0, "compact": 1.0},
            "routes_compact": {"structural": 3},
            "fallback_rate": 0.0,
        },
        {
            "env_id": "browsergym/miniwob.enter-text",
            "run_id": "b",
            "n_steps": 2,
            "success": False,
            "reward": 0.0,
            "latency_s": 0.7,
            "tokens": {"vision_full_state": 800, "full_state": 200, "compact": 200},
            "next_action": {"vision_full_state": 0.5, "full_state": 0.5, "compact": 0.5},
            "routes_compact": {"image_crop": 2},
            "fallback_rate": 1.0,
        },
        {"env_id": "browsergym/miniwob.broken", "run_id": "c", "error": "RuntimeError: boom"},
    ]

    report = aggregate_suite_report(per_run, predictor="heuristic")

    assert report["n_tasks"] == 3 and report["n_tasks_ok"] == 2
    assert report["n_steps"] == 5
    assert report["success_rate"] == 0.5
    assert report["tokens"]["totals"]["compact"] == 320
    assert report["tokens"]["savings_pct"]["compact_vs_vision_full_state"] == pytest.approx(
        82.22, abs=0.1
    )
    assert report["next_action_accuracy"]["compact"] == 0.75
    reasons = {f["reason"] for f in report["failures"]}
    assert "RuntimeError: boom" in reasons
    assert "episode_not_solved" in reasons
