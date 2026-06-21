"""Adapter: BrowserGym / MiniWoB++ episodes -> BrowserDelta run records.

BrowserGym is an *optional* dependency (the ``external-evals`` extra). Nothing in
core BrowserDelta imports it; this module raises a helpful error if it is missing.

The conversion of a BrowserGym observation into BrowserDelta's run schema does not
require BrowserGym itself -- it only reads documented fields of the observation
dict (``url``, ``axtree_object``, ``screenshot``, ...), so it is fully unit
testable with a mock observation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from browserdelta.schemas import (
    ActionResult,
    BoundingBox,
    BrowserAction,
    InteractiveElement,
    PageState,
    RunManifest,
    StatePointer,
    StepRecord,
)
from browserdelta.storage import append_jsonl, run_dir, write_json, write_manifest

INSTALL_HINT = (
    "BrowserGym is not installed. Install the optional extra with:\n"
    '    pip install -e ".[external-evals]"\n'
    "MiniWoB++ also needs its HTML served and MINIWOB_URL set, e.g.:\n"
    '    export MINIWOB_URL="file:///path/to/miniwob-plusplus/miniwob/html/miniwob/"'
)

# AX roles we treat as actionable interactive elements when no bid metadata says
# otherwise. Kept broad but excludes pure layout/text roles.
_INTERACTIVE_ROLES = {
    "button",
    "link",
    "textbox",
    "searchbox",
    "checkbox",
    "radio",
    "combobox",
    "listbox",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "option",
    "slider",
    "spinbutton",
    "switch",
    "tab",
    "textarea",
}

# AX action verb -> BrowserDelta action type. BrowserGym high-level actions are
# strings such as ``click('a12')`` or ``fill('a5', 'hi')``.
_ACTION_VERB_TO_TYPE = {
    "click": "click",
    "dblclick": "click",
    "hover": "click",
    "fill": "type",
    "type": "type",
    "press": "press",
    "keyboard_press": "press",
    "scroll": "scroll",
    "goto": "goto",
    "noop": "wait",
}


class BrowserGymUnavailable(ImportError):
    """Raised when an external-eval action needs BrowserGym but it is missing."""


def require_browsergym() -> Any:
    """Import and return BrowserGym, registering MiniWoB envs. Raises a helpful
    error if the optional dependency is not installed."""

    try:
        import gymnasium as gym  # noqa: F401
        import browsergym.core  # noqa: F401
        import browsergym.miniwob  # noqa: F401  (registers miniwob/* env ids)
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise BrowserGymUnavailable(INSTALL_HINT) from exc

    import gymnasium as gym

    return gym


def _prop_map(node: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for prop in node.get("properties", []):
        value = prop.get("value", {})
        if "value" in value:
            out[prop["name"]] = value["value"]
    return out


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in ("true", "false"):
        return value == "true"
    return None


def _bbox_from_extra(extra: dict[str, Any] | None, bid: str) -> BoundingBox | None:
    if not extra or bid not in extra:
        return None
    box = extra[bid].get("bbox")
    if not box or len(box) != 4:
        return None
    return BoundingBox(x=float(box[0]), y=float(box[1]), width=float(box[2]), height=float(box[3]))


def axtree_to_interactive(
    axtree: dict[str, Any],
    extra_properties: dict[str, Any] | None = None,
) -> list[InteractiveElement]:
    """Extract interactive elements from a BrowserGym/CDP accessibility tree."""

    elements: list[InteractiveElement] = []
    for node in axtree.get("nodes", []):
        bid = node.get("browsergym_id")
        if not bid:
            continue
        role = node.get("role", {}).get("value", "")
        props = _prop_map(node)
        extra = (extra_properties or {}).get(bid, {})
        clickable = bool(extra.get("clickable"))
        if role not in _INTERACTIVE_ROLES and not clickable:
            continue
        name = node.get("name", {}).get("value", "") or ""
        value = node.get("value", {}).get("value")
        elements.append(
            InteractiveElement(
                ref=bid,
                role=role or "generic",
                name=name,
                value=str(value) if value is not None else None,
                disabled=_as_bool(props.get("disabled")),
                checked=_as_bool(props.get("checked")),
                selected=_as_bool(props.get("selected")),
                expanded=_as_bool(props.get("expanded")),
                bbox=_bbox_from_extra(extra_properties, bid),
                attributes={"clickable": clickable} if clickable else {},
            )
        )
    return elements


def axtree_to_text(axtree: dict[str, Any]) -> list[str]:
    """Flatten visible node names into text lines (lightweight, no BrowserGym)."""

    lines: list[str] = []
    for node in axtree.get("nodes", []):
        role = node.get("role", {}).get("value", "")
        if role in {"", "generic", "none", "presentation", "InlineTextBox"}:
            continue
        name = node.get("name", {}).get("value", "") or ""
        name = name.strip()
        if name:
            lines.append(name)
    return lines


def _goal_text(obs: dict[str, Any]) -> str:
    goal = obs.get("goal")
    if isinstance(goal, str) and goal.strip():
        return goal.strip()
    parts: list[str] = []
    for message in obs.get("goal_object", []) or []:
        if isinstance(message, dict) and message.get("type") == "text":
            parts.append(str(message.get("text", "")))
    return " ".join(p for p in parts if p).strip()


def _title(obs: dict[str, Any]) -> str:
    titles = obs.get("open_pages_titles")
    index = obs.get("active_page_index")
    if titles:
        try:
            idx = int(index[0]) if index is not None else 0
        except (TypeError, ValueError, IndexError):
            idx = 0
        if 0 <= idx < len(titles):
            return str(titles[idx])
    return ""


def observation_to_page_state(
    obs: dict[str, Any],
    screenshot: str | None = None,
) -> PageState:
    """Convert a BrowserGym observation dict into a BrowserDelta PageState."""

    axtree = obs.get("axtree_object") or {"nodes": []}
    extra = obs.get("extra_element_properties")
    return PageState(
        url=str(obs.get("url", "")),
        title=_title(obs),
        text=axtree_to_text(axtree),
        interactive=axtree_to_interactive(axtree, extra),
        focused_ref=obs.get("focused_element_bid") or None,
        screenshot=screenshot,
        metadata={
            "goal": _goal_text(obs),
            "last_action": obs.get("last_action"),
            "last_action_error": obs.get("last_action_error") or None,
        },
    )


def parse_action(action: str | None) -> BrowserAction:
    """Map a BrowserGym high-level action string to a BrowserAction."""

    if not action:
        return BrowserAction(type="wait", metadata={"raw_action": action})

    text = action.strip()
    verb = text.split("(", 1)[0].strip()
    action_type = _ACTION_VERB_TO_TYPE.get(verb, "click")

    args: list[str] = []
    if "(" in text and text.endswith(")"):
        inner = text[text.index("(") + 1 : -1].strip()
        if inner:
            args = [a.strip().strip("'\"") for a in inner.split(",")]

    target = args[0] if args else None
    payload = args[1] if len(args) > 1 else None
    return BrowserAction(
        type=action_type,
        target=target,
        text=payload if action_type == "type" else None,
        key=payload if action_type == "press" else None,
        metadata={"raw_action": text, "source": "browsergym"},
    )


def _save_screenshot(array: Any, path: Path) -> bool:
    if array is None:
        return False
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array).save(path)
    return True


def _write_state(run_path: Path, step: int, when: str, obs: dict[str, Any]) -> StatePointer:
    shot_rel = f"steps/step_{step:03d}_{when}.png"
    state_rel = f"steps/step_{step:03d}_{when}.json"
    has_shot = _save_screenshot(obs.get("screenshot"), run_path / shot_rel)
    state = observation_to_page_state(obs, screenshot=shot_rel if has_shot else None)
    write_json(run_path / state_rel, state)
    return StatePointer(screenshot=shot_rel if has_shot else "", state=state_rel)


def noop_policy(_obs: dict[str, Any]) -> str:
    """Default policy: do nothing. Real solving needs an LLM/agent policy."""

    return "noop()"


def record_episode(
    env_id: str,
    run_id: str,
    *,
    max_steps: int = 10,
    headless: bool = True,
    policy: Callable[[dict[str, Any]], str] | None = None,
    actions: list[str] | None = None,
    compact: bool = False,
    gym_module: Any | None = None,
) -> Path:
    """Run one BrowserGym episode and write it as a BrowserDelta run.

    ``gym_module`` is an injection point for tests (a fake gymnasium). In normal
    use it is resolved via :func:`require_browsergym`.
    """

    gym = gym_module or require_browsergym()
    scripted = list(actions) if actions else None
    choose = policy or noop_policy

    env = gym.make(env_id, headless=headless)
    run_path = run_dir(run_id)
    steps_path = run_path / "steps.jsonl"
    if steps_path.exists():
        steps_path.unlink()

    reset_out = env.reset()
    obs = reset_out[0] if isinstance(reset_out, tuple) else reset_out
    write_manifest(
        run_path,
        RunManifest(
            run_id=run_id,
            start_url=str(obs.get("url", "")),
            mode="local",
            metadata={"source": "browsergym", "env_id": env_id, "goal": _goal_text(obs)},
        ),
    )

    last_reward = 0.0
    success = False
    for step in range(1, max_steps + 1):
        if scripted is not None:
            if step - 1 >= len(scripted):
                break
            action = scripted[step - 1]
        else:
            action = choose(obs)

        before = _write_state(run_path, step, "before", obs)
        step_out = env.step(action)
        next_obs, reward, terminated, truncated, info = step_out
        obs = next_obs
        after = _write_state(run_path, step, "after", obs)

        last_reward = float(reward)
        success = success or bool(info.get("success", reward and reward > 0))
        append_jsonl(
            steps_path,
            StepRecord(
                step=step,
                action=parse_action(action),
                result=ActionResult(
                    ok=not bool(obs.get("last_action_error")),
                    message=str(info.get("task_info", "")),
                    error=obs.get("last_action_error") or None,
                ),
                before=before,
                after=after,
            ),
        )
        if terminated or truncated:
            break

    env.close()

    manifest_path = run_path / "run.json"
    manifest = RunManifest.model_validate(json.loads(manifest_path.read_text()))
    manifest.metadata.update({"reward": last_reward, "success": success})
    write_json(manifest_path, manifest)

    if compact:
        from browserdelta.compaction.codec import compact_run

        compact_run(run_path)

    return run_path
