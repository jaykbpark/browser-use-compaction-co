from __future__ import annotations

import base64
import json
import mimetypes
import shutil
import sys
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, Protocol

from browserdelta.compaction.codec import compact_step
from browserdelta.compaction.metrics import (
    estimate_raw_baseline_tokens,
    estimate_state_tokens,
    estimate_text_tokens,
    reduction_pct,
)
from browserdelta.compaction.renderer import (
    render_adaptive_state_context,
    render_interactive_context,
)
from browserdelta.eval.llm_agent import _ACTION_SCHEMA, _extract_json_payload, _post_json
from browserdelta.observability.arize import ArizeEvalTracer, noop_arize_tracer
from browserdelta.external.browsergym_adapter import (
    BrowserGymUnavailable,
    format_browsergym_action,
    observation_to_page_state,
    parse_browsergym_action,
    require_browsergym,
    write_browsergym_state,
)
from browserdelta.schemas import (
    ActionResult,
    BrowserAction,
    CompactObservation,
    InteractiveElement,
    PageState,
    ReplayContextMode,
    RunManifest,
    StepRecord,
)
from browserdelta.storage import (
    append_jsonl,
    read_manifest,
    run_dir,
    write_compact_observations,
    write_json,
    write_manifest,
)


LiveMode = Literal["compact", "full_state", "vision_full_state"]
PolicyFactory = Callable[[LiveMode, dict[str, Any]], "BrowserGymLivePolicy"]

WORKARENA_HINT = (
    "WorkArena is optional and is not installed in this environment. Install the "
    "BrowserGym WorkArena package in the isolated BrowserGym environment, then "
    "run this script with --suite-kind workarena."
)


class BrowserGymLivePolicy(Protocol):
    name: str

    def choose_action(
        self,
        *,
        goal: str,
        observation: CompactObservation,
        page_state: PageState,
        previous_action: BrowserAction | None,
        action_history: list[BrowserAction],
        mode: LiveMode,
        max_steps: int | None = None,
        artifact_root: Path | None = None,
    ) -> BrowserAction:
        ...


class ScriptedBrowserGymPolicy:
    name = "scripted"

    def __init__(self, actions: list[str | BrowserAction]) -> None:
        self._actions = [
            parse_browsergym_action(action) if isinstance(action, str) else action
            for action in actions
        ]
        self._index = 0

    def choose_action(
        self,
        *,
        goal: str,
        observation: CompactObservation,
        page_state: PageState,
        previous_action: BrowserAction | None,
        action_history: list[BrowserAction],
        mode: LiveMode,
        max_steps: int | None = None,
        artifact_root: Path | None = None,
    ) -> BrowserAction:
        del goal, observation, page_state, previous_action, action_history, mode, max_steps, artifact_root
        if self._index >= len(self._actions):
            return BrowserAction(type="wait")
        action = self._actions[self._index]
        self._index += 1
        return action


class HeuristicBrowserGymPolicy:
    name = "heuristic"

    def choose_action(
        self,
        *,
        goal: str,
        observation: CompactObservation,
        page_state: PageState,
        previous_action: BrowserAction | None,
        action_history: list[BrowserAction],
        mode: LiveMode,
        max_steps: int | None = None,
        artifact_root: Path | None = None,
    ) -> BrowserAction:
        del observation, previous_action, action_history, mode, max_steps, artifact_root
        goal_text = _normalize(goal)
        quoted = _quoted_text(goal)
        wants_text_entry = any(word in goal_text for word in ("enter", "type", "write", "fill"))
        wants_click = any(word in goal_text for word in ("click", "press", "select", "choose"))
        textbox = _first_enabled(page_state.interactive, {"textbox", "searchbox", "textarea"})
        if textbox and quoted and wants_text_entry and not wants_click:
            return BrowserAction(type="type", target=textbox.ref, text=quoted[0])

        for element in page_state.interactive:
            if element.disabled:
                continue
            aliases = _element_aliases(element)
            if aliases and any(alias and alias in goal_text for alias in aliases):
                if wants_click and element.role in {"textbox", "searchbox", "textarea"}:
                    continue
                return _default_action_for_element(element)

        fallback = _first_enabled(
            page_state.interactive,
            {"button", "link", "checkbox", "radio", "option", "combobox"},
        )
        if fallback:
            return _default_action_for_element(fallback)
        return BrowserAction(type="wait")


class LLMBrowserGymPolicy:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
        transport: Callable[[str, dict[str, Any], dict[str, str], float], dict[str, Any]]
        | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport or _post_json
        self.name = f"llm:{model}"

    def choose_action(
        self,
        *,
        goal: str,
        observation: CompactObservation,
        page_state: PageState,
        previous_action: BrowserAction | None,
        action_history: list[BrowserAction],
        mode: LiveMode,
        max_steps: int | None = None,
        artifact_root: Path | None = None,
    ) -> BrowserAction:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for LLMBrowserGymPolicy.")

        context = {
            "goal": goal,
            "mode": mode,
            "step_number": len(action_history) + 1,
            "max_steps": max_steps,
            "steps_remaining": max(max_steps - len(action_history), 0)
            if max_steps is not None
            else None,
            "previous_action": previous_action.model_dump(mode="json")
            if previous_action
            else None,
            "action_history": [
                action.model_dump(mode="json") for action in action_history[-8:]
            ],
            "current_observation": _observation_payload(observation),
        }
        if mode == "compact":
            context["current_page_state"] = None
            context["state_scope"] = (
                "compact_observation_only: use refs and hints in current_observation; "
                "full visible text and full accessibility state are intentionally omitted."
            )
        else:
            context["current_page_state"] = _page_payload(page_state)
        image_url = (
            _image_data_url(observation, artifact_root)
            if mode == "vision_full_state"
            else None
        )
        user_content: str | list[dict[str, str]]
        if image_url:
            user_content = [
                {"type": "input_text", "text": json.dumps(context)},
                {"type": "input_image", "image_url": image_url},
            ]
        else:
            user_content = json.dumps(context)
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": _LIVE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "browser_action_prediction",
                    "schema": _ACTION_SCHEMA,
                    "strict": True,
                }
            },
            "temperature": 0,
            "store": False,
        }
        response = self.transport(
            f"{self.base_url}/responses",
            payload,
            {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            self.timeout,
        )
        parsed = _extract_json_payload(response)
        return BrowserAction(
            type=parsed["type"],
            target=parsed.get("target"),
            text=parsed.get("text"),
            key=parsed.get("key"),
            amount=parsed.get("amount"),
            url=parsed.get("url"),
        )


def run_live_episode(
    env_id: str,
    run_id: str,
    *,
    mode: LiveMode = "compact",
    policy: BrowserGymLivePolicy | None = None,
    max_steps: int = 10,
    headless: bool = True,
    seed: int | None = None,
    goal: str | None = None,
    gym_module: Any | None = None,
    arize_tracer: ArizeEvalTracer | None = None,
) -> dict[str, Any]:
    if mode not in {"compact", "full_state", "vision_full_state"}:
        raise ValueError("mode must be compact, full_state, or vision_full_state.")

    gym = gym_module or require_browsergym(extra_modules=_extra_modules_for_env(env_id))
    policy = policy or HeuristicBrowserGymPolicy()
    trace = arize_tracer or noop_arize_tracer()
    env = gym.make(env_id, headless=headless)
    run_path = run_dir(run_id)
    shutil.rmtree(run_path)
    run_path = run_dir(run_id)
    steps_path = run_path / "steps.jsonl"

    compact_observations: list[CompactObservation] = []
    action_history: list[BrowserAction] = []
    decisions: list[dict[str, Any]] = []
    reward = 0.0
    success = False
    terminated = False
    truncated = False
    error: str | None = None
    start = time.monotonic()
    episode_cm = trace.live_episode_span(
        env_id=env_id,
        run_id=run_id,
        mode=mode,
        policy=policy.name,
        goal=goal or env_id,
    )
    episode_span = episode_cm.__enter__()

    try:
        obs = _reset_env(env, seed)
        initial_state = observation_to_page_state(obs)
        effective_goal = goal or str(initial_state.metadata.get("goal") or "")
        write_manifest(
            run_path,
            RunManifest(
                run_id=run_id,
                start_url=initial_state.url,
                mode="local",
                metadata={
                    "source": "browsergym-live",
                    "env_id": env_id,
                    "goal": effective_goal,
                    "policy": policy.name,
                    "observation_mode": mode,
                    "seed": seed,
                },
            ),
        )

        previous_action: BrowserAction | None = None
        previous_compact: CompactObservation | None = None
        for step_number in range(1, max_steps + 1):
            before = write_browsergym_state(run_path, step_number, "before", obs)
            page_state = observation_to_page_state(
                obs,
                screenshot=before.screenshot or None,
            )
            decision_observation = _decision_observation(
                mode=mode,
                page_state=page_state,
                run_path=run_path,
                screenshot=before.screenshot,
                step_number=step_number,
                previous_compact=previous_compact,
            )
            with trace.live_step_span(
                env_id=env_id,
                run_id=run_id,
                mode=mode,
                step=step_number,
                observation=decision_observation,
            ) as step_span:
                raw_action = policy.choose_action(
                    goal=effective_goal,
                    observation=decision_observation,
                    page_state=page_state,
                    previous_action=previous_action,
                    action_history=action_history,
                    mode=mode,
                    max_steps=max_steps,
                    artifact_root=run_path,
                )
                resolved_action = resolve_action_for_page(raw_action, page_state)
                resolved_action = _apply_compact_hint_guard(
                    resolved_action,
                    page_state,
                    decision_observation,
                    action_history,
                    mode,
                )
                action_text = format_browsergym_action(resolved_action)
                decision_row = {
                    "step": step_number,
                    "mode": mode,
                    "observation_summary": decision_observation.summary,
                    "tokens_estimate": decision_observation.tokens_estimate,
                    "baseline_tokens_estimate": decision_observation.baseline_tokens_estimate,
                    "raw_action": raw_action.model_dump(mode="json"),
                    "resolved_action": resolved_action.model_dump(mode="json"),
                    "browsergym_action": action_text,
                }
                trace.record_live_step(step_span, decision_row)
                decisions.append(decision_row)

            step_out = env.step(action_text)
            obs, reward, terminated, truncated, info = _unpack_step(step_out)
            after = write_browsergym_state(run_path, step_number, "after", obs)
            success = success or bool(info.get("success") or reward > 0)
            last_error = obs.get("last_action_error") or None
            record = StepRecord(
                step=step_number,
                action=parse_browsergym_action(action_text),
                result=ActionResult(
                    ok=not bool(last_error),
                    message=str(info.get("task_info") or ""),
                    error=last_error,
                ),
                before=before,
                after=after,
            )
            append_jsonl(steps_path, record)

            if mode == "compact":
                previous_compact = compact_step(run_path, record)
                compact_observations.append(previous_compact)
            previous_action = record.action
            action_history.append(record.action)
            if terminated or truncated:
                break
    except Exception as exc:
        error = str(exc)
        trace.record_live_episode(
            episode_span,
            _errored_result({"env_id": env_id, "goal": goal or ""}, mode, error, 1),
        )
        raise
    finally:
        env.close()
        if compact_observations:
            write_compact_observations(run_path, compact_observations)
        if (run_path / "run.json").exists():
            manifest = read_manifest(run_path)
            manifest.metadata.update(
                {
                    "reward": float(reward),
                    "success": bool(success),
                    "terminated": bool(terminated),
                    "truncated": bool(truncated),
                    "steps": len(decisions),
                    "error": error,
                    "duration_sec": round(time.monotonic() - start, 3),
                }
            )
            write_json(run_path / "run.json", manifest)
        if error is None:
            token_total = sum(int(row["tokens_estimate"]) for row in decisions)
            baseline_total = sum(int(row["baseline_tokens_estimate"]) for row in decisions)
            trace.record_live_episode(
                episode_span,
                {
                    "schema_version": 1,
                    "env_id": env_id,
                    "run_id": run_id,
                    "run_path": str(run_path),
                    "mode": mode,
                    "policy": policy.name,
                    "goal": effective_goal,
                    "success": bool(success),
                    "reward": float(reward),
                    "terminated": bool(terminated),
                    "truncated": bool(truncated),
                    "steps": len(decisions),
                    "decision_tokens": token_total,
                    "baseline_tokens": baseline_total,
                    "token_reduction_pct": reduction_pct(baseline_total, token_total),
                    "error": error,
                    "decisions": decisions,
                },
            )
        episode_cm.__exit__(*sys.exc_info())

    token_total = sum(int(row["tokens_estimate"]) for row in decisions)
    baseline_total = sum(int(row["baseline_tokens_estimate"]) for row in decisions)
    return {
        "schema_version": 1,
        "env_id": env_id,
        "run_id": run_id,
        "run_path": str(run_path),
        "mode": mode,
        "policy": policy.name,
        "goal": effective_goal,
        "success": bool(success),
        "reward": float(reward),
        "terminated": bool(terminated),
        "truncated": bool(truncated),
        "steps": len(decisions),
        "decision_tokens": token_total,
        "baseline_tokens": baseline_total,
        "token_reduction_pct": reduction_pct(baseline_total, token_total),
        "error": error,
        "decisions": decisions,
    }


def run_live_suite(
    suite: dict[str, Any],
    *,
    modes: list[LiveMode] | None = None,
    policy_factory: PolicyFactory | None = None,
    max_steps: int = 10,
    headless: bool = True,
    seed: int | None = None,
    retries: int = 0,
    limit: int | None = None,
    suite_kind: str = "miniwob",
    gym_module: Any | None = None,
    arize_tracer: ArizeEvalTracer | None = None,
    policy_name: str | None = None,
) -> dict[str, Any]:
    modes = modes or ["compact", "full_state"]
    policy_factory = policy_factory or _default_policy_factory
    episodes = _episodes_from_suite(
        suite,
        limit=limit,
        suite_kind=suite_kind,
        gym_module=gym_module,
    )
    trace = arize_tracer or noop_arize_tracer()

    runs: list[dict[str, Any]] = []
    failure_table: list[dict[str, Any]] = []
    suite_name = str(suite.get("suite") or f"browsergym-live-{suite_kind}")
    with trace.live_suite_span(
        suite=suite_name,
        policy=policy_name or str(suite.get("policy") or "policy_factory"),
        modes=list(modes),
    ) as suite_span:
        for episode_index, episode in enumerate(episodes, start=1):
            by_mode: dict[str, dict[str, Any]] = {}
            for mode in modes:
                result = _run_with_retries(
                    episode,
                    mode=mode,
                    policy_factory=policy_factory,
                    max_steps=int(episode.get("max_steps") or max_steps),
                    headless=headless,
                    seed=int(episode.get("seed", seed if seed is not None else episode_index)),
                    retries=retries,
                    gym_module=gym_module,
                    arize_tracer=trace,
                )
                by_mode[mode] = result
                runs.append(result)
            failure_table.append(_failure_row(episode, by_mode, modes))

        report = {
            "schema_version": 1,
            "suite": suite_name,
            "source": "browsergym-live",
            "suite_kind": suite_kind,
            "modes": modes,
            "runs": runs,
            "failure_table": failure_table,
            "summary": _suite_summary(runs, failure_table, modes),
            "charts": _chart_payload(runs, failure_table, modes),
        }
        trace.record_live_suite(suite_span, report)
        return report


def probe_workarena(gym_module: Any | None = None) -> dict[str, Any]:
    try:
        gym = gym_module or require_browsergym(extra_modules=["browsergym.workarena"])
    except BrowserGymUnavailable as exc:
        return {
            "available": False,
            "env_count": 0,
            "env_ids": [],
            "message": f"{WORKARENA_HINT}\n{exc}",
        }
    env_ids = list_browsergym_env_ids(prefix="browsergym/workarena", gym_module=gym)
    return {
        "available": bool(env_ids),
        "env_count": len(env_ids),
        "env_ids": env_ids,
        "message": "WorkArena BrowserGym envs are registered." if env_ids else WORKARENA_HINT,
    }


def list_browsergym_env_ids(
    *,
    prefix: str = "browsergym/miniwob",
    gym_module: Any | None = None,
) -> list[str]:
    gym = gym_module or require_browsergym()
    registry = getattr(getattr(gym, "envs", None), "registry", {})
    values = registry.values() if hasattr(registry, "values") else registry
    ids: list[str] = []
    for spec in values:
        env_id = str(getattr(spec, "id", spec))
        if env_id.startswith(prefix):
            ids.append(env_id)
    return sorted(set(ids))


def resolve_action_for_page(action: BrowserAction, page_state: PageState) -> BrowserAction:
    if action.type in {"wait", "goto", "scroll"}:
        return action
    if action.type in {"type", "press"} and not action.target and page_state.focused_ref:
        action = action.model_copy(update={"target": page_state.focused_ref})
    if action.type == "type" and not action.target:
        return BrowserAction(type="wait")
    if action.type == "click" and not action.target:
        fallback = _first_enabled(
            page_state.interactive,
            {"button", "link", "checkbox", "radio", "option", "combobox"},
        )
        if fallback:
            return action.model_copy(update={"target": fallback.ref})
        return BrowserAction(type="wait")
    if not action.target:
        return action
    resolved = _resolve_target_ref(action.target, page_state.interactive)
    return action.model_copy(update={"target": resolved})


def _apply_compact_hint_guard(
    action: BrowserAction,
    page_state: PageState,
    observation: CompactObservation,
    action_history: list[BrowserAction],
    mode: LiveMode,
) -> BrowserAction:
    if mode != "compact" or action.type != "click" or not action.target:
        return action
    if "not visible in active panel" not in observation.llm_observation:
        return action
    if "inactive_tabs=" not in observation.llm_observation:
        return action

    clicked = {_normalize(previous.target) for previous in action_history if previous.target}
    target = next(
        (
            item
            for item in page_state.interactive
            if _normalize(item.ref) == _normalize(action.target)
        ),
        None,
    )
    if target is None:
        return action

    inactive_tabs = [
        item
        for item in page_state.interactive
        if item.role == "tab" and not item.selected and not item.disabled
    ]
    if not inactive_tabs:
        return action
    replacement = next(
        (item for item in inactive_tabs if _normalize(item.ref) not in clicked),
        inactive_tabs[0],
    )
    if (
        target.role == "tab"
        and _normalize(target.ref) in clicked
        and _normalize(replacement.ref) != _normalize(target.ref)
    ):
        metadata = {
            **action.metadata,
            "browserdelta_hint_override": "unvisited_tab_before_revisited_tab",
            "original_target": action.target,
        }
        return action.model_copy(update={"target": replacement.ref, "metadata": metadata})

    if target.role != "generic" or target.name or target.value:
        return action

    metadata = {
        **action.metadata,
        "browserdelta_hint_override": "inactive_tab_before_unlabeled_click",
        "original_target": action.target,
    }
    return action.model_copy(update={"target": replacement.ref, "metadata": metadata})


def write_live_markdown_report(path: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    lines = [
        f"# {report['suite']}",
        "",
        "## Summary",
        "",
        f"- Modes: {', '.join(report['modes'])}",
        f"- Episodes: {summary['episodes']}",
        f"- Comparison rows: {len(report['failure_table'])}",
        "",
        "| Mode | Success | Success rate | Avg tokens | Avg steps |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in summary["by_mode"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["mode"],
                    f"{row['successes']}/{row['episodes']}",
                    f"{row['success_rate'] * 100:.1f}%",
                    str(row["avg_decision_tokens"]),
                    str(row["avg_steps"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Failure Table",
            "",
            "| Env | Compact | Baseline | Class | Saved |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in report["failure_table"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["env_id"],
                    _status(row.get("compact_success")),
                    _status(row.get("baseline_success")),
                    row["failure_class"],
                    f"{row['token_reduction_pct']:.2f}%",
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n")


def _decision_observation(
    *,
    mode: LiveMode,
    page_state: PageState,
    run_path: Path,
    screenshot: str,
    step_number: int,
    previous_compact: CompactObservation | None,
) -> CompactObservation:
    if mode == "compact" and previous_compact is not None:
        return previous_compact

    screenshot_path = run_path / screenshot if screenshot else Path("__missing__")
    baseline_tokens = (
        estimate_raw_baseline_tokens(page_state, screenshot_path)
        if screenshot
        else estimate_state_tokens(page_state)
    )
    if mode == "compact":
        llm_observation = _render_initial_compact(page_state)
        compact_tokens = estimate_text_tokens(llm_observation)
        return CompactObservation(
            step=step_number,
            action_result="current",
            summary="Initial browser state.",
            changed=[],
            interactive=page_state.interactive[:30],
            fallback="none",
            route="text_only",
            route_reason="Initial state for a live BrowserGym episode.",
            confidence=1.0,
            llm_observation=llm_observation,
            crop_paths=[],
            tokens_estimate=compact_tokens,
            baseline_tokens_estimate=baseline_tokens,
            reduction_pct=reduction_pct(baseline_tokens, compact_tokens),
        )

    llm_observation = _render_full_state(page_state, screenshot, mode)
    return CompactObservation(
        step=step_number,
        action_result="current",
        summary=f"{_mode_label(mode)} current browser state.",
        changed=[],
        interactive=page_state.interactive,
        fallback="full_screenshot",
        route="full_screenshot",
        route_reason=f"{_mode_label(mode)} live baseline.",
        confidence=1.0,
        llm_observation=llm_observation,
        crop_paths=[],
        full_screenshot_path=screenshot or None,
        tokens_estimate=max(baseline_tokens, estimate_text_tokens(llm_observation)),
        baseline_tokens_estimate=baseline_tokens,
        reduction_pct=0.0,
    )


def _render_initial_compact(page_state: PageState) -> str:
    lines = ["Current browser state."]
    if page_state.url:
        lines.append(f"URL: {page_state.url}")
    if page_state.title:
        lines.append(f"Title: {page_state.title}")
    if page_state.text:
        lines.append("Visible text: " + "; ".join(page_state.text[:12]))
    lines.extend(render_adaptive_state_context(page_state))
    if page_state.interactive:
        lines.append(
            "Current interactive elements: "
            + "; ".join(render_interactive_context(page_state.interactive))
        )
    if page_state.focused_ref:
        lines.append(f"Focused element ref: {page_state.focused_ref}")
    return "\n".join(lines)


def _render_full_state(page_state: PageState, screenshot: str, mode: LiveMode) -> str:
    screenshot_hint = (
        f"{screenshot} (attached as input_image)" if mode == "vision_full_state" else screenshot
    )
    lines = [
        f"{_mode_label(mode).upper()} CONTEXT",
        f"URL: {page_state.url}",
        f"Title: {page_state.title or '(none)'}",
        f"Screenshot: {screenshot_hint or '(none)'}",
    ]
    if page_state.text:
        lines.append("Visible text:")
        lines.extend(f"- {line}" for line in page_state.text)
    if page_state.interactive:
        lines.append("Current interactive elements:")
        lines.extend(f"- {_render_interactive(item)}" for item in page_state.interactive)
    if page_state.focused_ref:
        lines.append(f"Focused element ref: {page_state.focused_ref}")
    return "\n".join(lines)


def _run_with_retries(
    episode: dict[str, Any],
    *,
    mode: LiveMode,
    policy_factory: PolicyFactory,
    max_steps: int,
    headless: bool,
    seed: int,
    retries: int,
    gym_module: Any | None,
    arize_tracer: ArizeEvalTracer | None,
) -> dict[str, Any]:
    last_error: str | None = None
    for attempt in range(retries + 1):
        run_id = _mode_run_id(episode, mode, attempt if retries else None)
        try:
            result = run_live_episode(
                str(episode["env_id"]),
                run_id,
                mode=mode,
                policy=policy_factory(mode, episode),
                max_steps=max_steps,
                headless=headless,
                seed=seed,
                goal=str(episode.get("goal") or ""),
                gym_module=gym_module,
                arize_tracer=arize_tracer,
            )
            result["attempt"] = attempt + 1
            return result
        except BrowserGymUnavailable:
            raise
        except Exception as exc:
            last_error = str(exc)
    return _errored_result(episode, mode, last_error or "unknown error", retries + 1)


def _episodes_from_suite(
    suite: dict[str, Any],
    *,
    limit: int | None,
    suite_kind: str,
    gym_module: Any | None,
) -> list[dict[str, Any]]:
    episodes = suite.get("episodes")
    if episodes is None and "envs" in suite:
        episodes = [
            {"env_id": entry} if isinstance(entry, str) else entry for entry in suite["envs"]
        ]
    if episodes is None:
        prefix = "browsergym/workarena" if suite_kind == "workarena" else "browsergym/miniwob"
        episodes = [
            {"env_id": env_id}
            for env_id in list_browsergym_env_ids(prefix=prefix, gym_module=gym_module)
        ]
    if not isinstance(episodes, list):
        raise ValueError("Live suite JSON must include episodes or envs as a list.")
    out = [
        {"env_id": entry} if isinstance(entry, str) else dict(entry)
        for entry in episodes
        if isinstance(entry, (dict, str))
    ]
    if limit is not None:
        out = out[:limit]
    if not out:
        raise ValueError("No BrowserGym live episodes were selected.")
    return out


def _failure_row(
    episode: dict[str, Any],
    by_mode: dict[str, dict[str, Any]],
    modes: list[LiveMode],
) -> dict[str, Any]:
    compact = by_mode.get("compact")
    baseline_mode = next((mode for mode in modes if mode != "compact"), None)
    baseline = by_mode.get(baseline_mode) if baseline_mode else None
    compact_success = _success_or_none(compact)
    baseline_success = _success_or_none(baseline)
    baseline_tokens = int((baseline or {}).get("decision_tokens") or 0)
    compact_tokens = int((compact or {}).get("decision_tokens") or 0)
    return {
        "env_id": str(episode["env_id"]),
        "compact_run_id": (compact or {}).get("run_id"),
        "baseline_mode": baseline_mode,
        "baseline_run_id": (baseline or {}).get("run_id"),
        "compact_success": compact_success,
        "baseline_success": baseline_success,
        "compact_steps": int((compact or {}).get("steps") or 0),
        "baseline_steps": int((baseline or {}).get("steps") or 0),
        "compact_tokens": compact_tokens,
        "baseline_tokens": baseline_tokens,
        "token_reduction_pct": reduction_pct(baseline_tokens, compact_tokens),
        "failure_class": _failure_class(compact_success, baseline_success, compact, baseline),
        "compact_error": (compact or {}).get("error"),
        "baseline_error": (baseline or {}).get("error"),
    }


def _suite_summary(
    runs: list[dict[str, Any]],
    failure_table: list[dict[str, Any]],
    modes: list[LiveMode],
) -> dict[str, Any]:
    by_mode: list[dict[str, Any]] = []
    for mode in modes:
        mode_runs = [run for run in runs if run.get("mode") == mode]
        successes = sum(1 for run in mode_runs if run.get("success"))
        token_total = sum(int(run.get("decision_tokens") or 0) for run in mode_runs)
        step_total = sum(int(run.get("steps") or 0) for run in mode_runs)
        by_mode.append(
            {
                "mode": mode,
                "episodes": len(mode_runs),
                "successes": successes,
                "success_rate": round(successes / len(mode_runs), 3) if mode_runs else 0.0,
                "decision_tokens": token_total,
                "avg_decision_tokens": round(token_total / len(mode_runs), 1)
                if mode_runs
                else 0.0,
                "avg_steps": round(step_total / len(mode_runs), 1) if mode_runs else 0.0,
            }
        )
    classes = Counter(row["failure_class"] for row in failure_table)
    return {
        "episodes": len(failure_table),
        "by_mode": by_mode,
        "failure_classes": dict(sorted(classes.items())),
        "compact_regressions": classes.get("compact_regression", 0),
    }


def _chart_payload(
    runs: list[dict[str, Any]],
    failure_table: list[dict[str, Any]],
    modes: list[LiveMode],
) -> dict[str, Any]:
    summary = _suite_summary(runs, failure_table, modes)
    return {
        "success_by_mode": [
            {
                "label": row["mode"],
                "successes": row["successes"],
                "episodes": row["episodes"],
                "rate": row["success_rate"],
            }
            for row in summary["by_mode"]
        ],
        "tokens_by_mode": [
            {"label": row["mode"], "tokens": row["decision_tokens"]}
            for row in summary["by_mode"]
        ],
        "failure_classes": [
            {"label": name, "count": count}
            for name, count in summary["failure_classes"].items()
        ],
    }


def _failure_class(
    compact_success: bool | None,
    baseline_success: bool | None,
    compact: dict[str, Any] | None,
    baseline: dict[str, Any] | None,
) -> str:
    if (compact or {}).get("error") or (baseline or {}).get("error"):
        return "runner_error"
    if compact_success is True and baseline_success is True:
        return "both_success"
    if compact_success is True and baseline_success is False:
        return "compact_only_success"
    if compact_success is False and baseline_success is True:
        return "compact_regression"
    if compact_success is False and baseline_success is False:
        return "both_failed"
    return "missing_mode"


def _errored_result(
    episode: dict[str, Any],
    mode: LiveMode,
    error: str,
    attempts: int,
) -> dict[str, Any]:
    run_id = _mode_run_id(episode, mode, attempts if attempts > 1 else None)
    return {
        "schema_version": 1,
        "env_id": str(episode["env_id"]),
        "run_id": run_id,
        "run_path": "",
        "mode": mode,
        "policy": "error",
        "goal": str(episode.get("goal") or ""),
        "success": False,
        "reward": 0.0,
        "terminated": False,
        "truncated": False,
        "steps": 0,
        "decision_tokens": 0,
        "baseline_tokens": 0,
        "token_reduction_pct": 0.0,
        "error": error,
        "attempt": attempts,
        "decisions": [],
    }


def _reset_env(env: Any, seed: int | None) -> dict[str, Any]:
    if seed is not None:
        try:
            reset_out = env.reset(seed=seed)
        except TypeError:
            reset_out = env.reset()
    else:
        reset_out = env.reset()
    return reset_out[0] if isinstance(reset_out, tuple) else reset_out


def _unpack_step(step_out: Any) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
    if not isinstance(step_out, tuple):
        raise TypeError("BrowserGym env.step() returned a non-tuple result.")
    if len(step_out) == 5:
        obs, reward, terminated, truncated, info = step_out
    elif len(step_out) == 4:
        obs, reward, done, info = step_out
        terminated, truncated = bool(done), False
    else:
        raise ValueError(f"BrowserGym env.step() returned {len(step_out)} values.")
    return obs, float(reward), bool(terminated), bool(truncated), dict(info or {})


def _default_policy_factory(_mode: LiveMode, episode: dict[str, Any]) -> BrowserGymLivePolicy:
    actions = episode.get("actions")
    if actions:
        return ScriptedBrowserGymPolicy([str(action) for action in actions])
    return HeuristicBrowserGymPolicy()


def _mode_run_id(
    episode: dict[str, Any],
    mode: LiveMode,
    attempt: int | None = None,
) -> str:
    base = str(episode.get("run_id") or _run_id_from_env(str(episode["env_id"])))
    suffix = f"_{mode}"
    if attempt is not None:
        suffix += f"_try{attempt}"
    return base + suffix


def _run_id_from_env(env_id: str) -> str:
    return "live_" + env_id.rsplit("/", 1)[-1].replace(".", "_").replace("-", "_")


def _extra_modules_for_env(env_id: str) -> list[str]:
    if "/workarena" in env_id or ".workarena" in env_id:
        return ["browsergym.workarena"]
    return []


def _resolve_target_ref(target: str, elements: list[InteractiveElement]) -> str:
    target_normalized = _normalize(target)
    for element in elements:
        if target_normalized == _normalize(element.ref):
            return element.ref
    for element in elements:
        if any(target_normalized == alias for alias in _element_aliases(element)):
            return element.ref
    for element in elements:
        if any(
            alias and (target_normalized in alias or alias in target_normalized)
            for alias in _element_aliases(element)
        ):
            return element.ref
    return target


def _element_aliases(element: InteractiveElement) -> list[str]:
    attrs = element.attributes or {}
    values = [
        element.ref,
        element.name,
        element.value or "",
        str(attrs.get("id") or ""),
        str(attrs.get("name") or ""),
        str(attrs.get("aria-label") or ""),
    ]
    return [_normalize(value) for value in values if value]


def _first_enabled(
    elements: list[InteractiveElement],
    roles: set[str],
) -> InteractiveElement | None:
    for element in elements:
        if element.disabled:
            continue
        if element.role in roles:
            return element
    return None


def _default_action_for_element(element: InteractiveElement) -> BrowserAction:
    if element.role in {"textbox", "searchbox", "textarea"}:
        return BrowserAction(type="type", target=element.ref, text="")
    if element.role == "combobox":
        return BrowserAction(type="click", target=element.ref)
    return BrowserAction(type="click", target=element.ref)


def _quoted_text(value: str) -> list[str]:
    out: list[str] = []
    start: int | None = None
    quote_char = ""
    for index, char in enumerate(value):
        if char in {"'", '"'} and start is None:
            start = index + 1
            quote_char = char
        elif start is not None and char == quote_char:
            out.append(value[start:index])
            start = None
            quote_char = ""
    return out


def _observation_payload(observation: CompactObservation) -> dict[str, Any]:
    return {
        "step": observation.step,
        "summary": observation.summary,
        "llm_observation": observation.llm_observation,
        "route": observation.route,
        "fallback": observation.fallback,
        "interactive_elements": [
            {
                "ref": item.ref,
                "role": item.role,
                "name": item.name,
                "value": item.value,
                "disabled": item.disabled,
                "checked": item.checked,
                "selected": item.selected,
            }
            for item in observation.interactive[:30]
        ],
    }


def _page_payload(page_state: PageState) -> dict[str, Any]:
    return {
        "url": page_state.url,
        "title": page_state.title,
        "visible_text": page_state.text[:40],
        "focused_ref": page_state.focused_ref,
        "interactive_elements": [
            {
                "ref": item.ref,
                "role": item.role,
                "name": item.name,
                "value": item.value,
                "disabled": item.disabled,
                "checked": item.checked,
                "selected": item.selected,
            }
            for item in page_state.interactive[:50]
        ],
    }


def _image_data_url(
    observation: CompactObservation,
    artifact_root: Path | None,
) -> str | None:
    if artifact_root is None or not observation.full_screenshot_path:
        return None
    root = artifact_root.resolve()
    image_path = (root / observation.full_screenshot_path).resolve()
    try:
        image_path.relative_to(root)
    except ValueError:
        return None
    if not image_path.exists():
        return None
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _render_interactive(item: InteractiveElement) -> str:
    label = item.name or item.value or item.ref
    state = []
    if item.disabled:
        state.append("disabled")
    if item.checked:
        state.append("checked")
    if item.selected:
        state.append("selected")
    suffix = f" ({', '.join(state)})" if state else ""
    return f"{item.ref} {item.role}: {label}{suffix}"


def _success_or_none(result: dict[str, Any] | None) -> bool | None:
    if result is None:
        return None
    return bool(result.get("success"))


def _status(value: Any) -> str:
    if value is None:
        return "missing"
    return "pass" if value else "fail"


def _mode_label(mode: ReplayContextMode) -> str:
    if mode == "vision_full_state":
        return "Vision full state"
    if mode == "full_state":
        return "Full state"
    return "Compact"


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).strip().lower().split())


_LIVE_SYSTEM_PROMPT = """You are a browser agent controlling a BrowserGym task.
Return one JSON browser action for the current browser state.

Rules:
- Use target refs exactly as shown in interactive_elements whenever possible.
- In compact mode, trust current_observation.llm_observation. It may include hints like remaining_refs, target_hint, or submit_ready_ref.
- If compact mode says target_status=target "... not visible in active panel" and inactive_tabs are listed, click an inactive tab before any unlabeled generic panel item.
- When choosing among inactive_tabs, prefer a tab ref that is not already present in action_history.
- Do not click unlabeled generic elements unless target_hint says they are the likely_click_ref or the target text is visible in the active panel.
- If submit_ready_ref is present and steps_remaining is 1 or less, click submit_ready_ref.
- BrowserGym tasks usually have short action budgets. Avoid repeating clicks that caused no state change; if a completion button is ready, click it.
- Choose one action type: goto, click, type, press, scroll, or wait.
- For type actions, include the exact text to type.
- If no useful action is available, return wait.
- Do not explain the observation; only return the structured action payload."""
