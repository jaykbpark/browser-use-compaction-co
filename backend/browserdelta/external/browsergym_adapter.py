from __future__ import annotations

import ast
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
    "BrowserGym is not installed in this Python environment.\n"
    "Use an isolated BrowserGym environment because current browsergym-core "
    "pins Playwright 1.44, while BrowserDelta's main recorder needs a newer "
    "Playwright. Example:\n"
    "  python -m venv .venv-browsergym\n"
    "  .venv-browsergym/bin/pip install browsergym-miniwob==0.14.3\n"
    "  PYTHONPATH=$PWD/backend .venv-browsergym/bin/python scripts/record_browsergym.py ...\n"
    "MiniWoB++ also requires MINIWOB_URL, for example:\n"
    "  export MINIWOB_URL=file:///path/to/miniwob-plusplus/miniwob/html/miniwob/"
)

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

_ACTION_VERB_TO_TYPE = {
    "click": "click",
    "dblclick": "click",
    "fill": "type",
    "goto": "goto",
    "keyboard_press": "press",
    "noop": "wait",
    "press": "press",
    "scroll": "scroll",
    "type": "type",
}


class BrowserGymUnavailable(ImportError):
    """Raised when BrowserGym-backed recording is requested but unavailable."""


def require_browsergym(extra_modules: list[str] | None = None) -> Any:
    try:
        import gymnasium as gym  # noqa: F401
        import browsergym.core  # noqa: F401
        import browsergym.miniwob  # noqa: F401
        for module in extra_modules or []:
            __import__(module)
    except ImportError as exc:
        raise BrowserGymUnavailable(INSTALL_HINT) from exc

    import gymnasium as gym

    return gym


def observation_to_page_state(obs: dict[str, Any], screenshot: str | None = None) -> PageState:
    axtree = obs.get("axtree_object") or {"nodes": []}
    return PageState(
        url=str(obs.get("url") or ""),
        title=_title(obs),
        text=axtree_to_text(axtree),
        interactive=axtree_to_interactive(axtree, obs.get("extra_element_properties")),
        focused_ref=obs.get("focused_element_bid") or None,
        screenshot=screenshot,
        metadata={
            "source": "browsergym",
            "goal": _goal_text(obs),
            "last_action": obs.get("last_action"),
            "last_action_error": obs.get("last_action_error") or None,
        },
    )


def axtree_to_interactive(
    axtree: dict[str, Any],
    extra_properties: dict[str, Any] | None = None,
) -> list[InteractiveElement]:
    elements: list[InteractiveElement] = []
    for node in axtree.get("nodes", []):
        ref = str(node.get("browsergym_id") or "")
        if not ref:
            continue

        role = _node_value(node, "role")
        extra = (extra_properties or {}).get(ref, {})
        clickable = bool(extra.get("clickable"))
        if role not in _INTERACTIVE_ROLES and not clickable:
            continue

        value = _node_value(node, "value")
        elements.append(
            InteractiveElement(
                ref=ref,
                role=role or "generic",
                name=_node_value(node, "name"),
                value=value or None,
                disabled=_bool_prop(node, "disabled"),
                checked=_bool_prop(node, "checked"),
                selected=_bool_prop(node, "selected"),
                expanded=_bool_prop(node, "expanded"),
                bbox=_bbox_from_extra(extra),
                attributes={"source": "browsergym", "clickable": clickable},
            )
        )
    return elements


def axtree_to_text(axtree: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for node in axtree.get("nodes", []):
        role = _node_value(node, "role")
        if role in {"", "generic", "none", "presentation", "InlineTextBox"}:
            continue
        name = _node_value(node, "name").strip()
        if name:
            lines.append(name)
    return lines


def parse_browsergym_action(action: str | None) -> BrowserAction:
    if not action:
        return BrowserAction(type="wait", metadata={"raw_action": action, "source": "browsergym"})

    text = action.strip()
    verb, args = _parse_call(text)
    action_type = _ACTION_VERB_TO_TYPE.get(verb, "click")
    target = str(args[0]) if args else None
    payload = str(args[1]) if len(args) > 1 else None

    return BrowserAction(
        type=action_type,
        target=target,
        text=payload if action_type == "type" else None,
        key=payload if action_type == "press" else None,
        url=target if action_type == "goto" else None,
        metadata={"raw_action": text, "source": "browsergym"},
    )


def format_browsergym_action(action: BrowserAction) -> str:
    if action.type == "wait":
        return "noop()"
    if action.type == "goto":
        return f"goto({_quote(action.url or action.target or '')})"
    if action.type == "type":
        return f"fill({_quote(action.target or '')}, {_quote(action.text or '')})"
    if action.type == "press":
        if action.target:
            return f"press({_quote(action.target)}, {_quote(action.key or 'Enter')})"
        return f"keyboard_press({_quote(action.key or 'Enter')})"
    if action.type == "scroll":
        return f"scroll(0, {int(action.amount or 0)})"
    return f"click({_quote(action.target or '')})"


def noop_policy(_obs: dict[str, Any]) -> str:
    return "noop()"


def record_episode(
    env_id: str,
    run_id: str,
    *,
    max_steps: int = 10,
    headless: bool = True,
    actions: list[str] | None = None,
    policy: Callable[[dict[str, Any]], str] | None = None,
    compact: bool = False,
    gym_module: Any | None = None,
) -> Path:
    gym = gym_module or require_browsergym()
    scripted = list(actions) if actions else None
    choose_action = policy or noop_policy

    env = gym.make(env_id, headless=headless)
    run_path = run_dir(run_id)
    steps_path = run_path / "steps.jsonl"
    if steps_path.exists():
        steps_path.unlink()

    try:
        reset_out = env.reset()
        obs = reset_out[0] if isinstance(reset_out, tuple) else reset_out

        write_manifest(
            run_path,
            RunManifest(
                run_id=run_id,
                start_url=str(obs.get("url") or ""),
                mode="local",
                metadata={
                    "source": "browsergym",
                    "env_id": env_id,
                    "goal": _goal_text(obs),
                    "policy": "scripted" if scripted else "noop",
                },
            ),
        )

        reward = 0.0
        success = False
        for step_number in range(1, max_steps + 1):
            if scripted is not None:
                if step_number - 1 >= len(scripted):
                    break
                action_text = scripted[step_number - 1]
            else:
                action_text = choose_action(obs)

            before = write_browsergym_state(run_path, step_number, "before", obs)
            step_out = env.step(action_text)
            obs, reward, terminated, truncated, info = _unpack_step(step_out)
            after = write_browsergym_state(run_path, step_number, "after", obs)
            success = success or bool(info.get("success") or reward > 0)

            append_jsonl(
                steps_path,
                StepRecord(
                    step=step_number,
                    action=parse_browsergym_action(action_text),
                    result=ActionResult(
                        ok=not bool(obs.get("last_action_error")),
                        message=str(info.get("task_info") or ""),
                        error=obs.get("last_action_error") or None,
                    ),
                    before=before,
                    after=after,
                ),
            )
            if terminated or truncated:
                break
    finally:
        env.close()

    manifest_path = run_path / "run.json"
    manifest = RunManifest.model_validate(json.loads(manifest_path.read_text()))
    manifest.metadata.update({"reward": float(reward), "success": success})
    write_json(manifest_path, manifest)

    if compact:
        from browserdelta.compaction.codec import compact_run

        compact_run(run_path)
    return run_path


def write_browsergym_state(
    run_path: Path,
    step: int,
    when: str,
    obs: dict[str, Any],
) -> StatePointer:
    screenshot_rel = f"steps/step_{step:03d}_{when}.png"
    state_rel = f"steps/step_{step:03d}_{when}.json"
    has_screenshot = _save_screenshot(obs.get("screenshot"), run_path / screenshot_rel)
    state = observation_to_page_state(obs, screenshot=screenshot_rel if has_screenshot else None)
    write_json(run_path / state_rel, state)
    return StatePointer(screenshot=screenshot_rel if has_screenshot else "", state=state_rel)


def _quote(value: str) -> str:
    return repr(str(value))


def _save_screenshot(value: Any, path: Path) -> bool:
    if value is None:
        return False
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(value).save(path)
    return True


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


def _parse_call(text: str) -> tuple[str, list[Any]]:
    try:
        parsed = ast.parse(text, mode="eval")
    except SyntaxError:
        return text.split("(", 1)[0].strip(), []
    if not isinstance(parsed.body, ast.Call):
        return text, []
    func = parsed.body.func
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    else:
        name = text.split("(", 1)[0].strip()
    args: list[Any] = []
    for arg in parsed.body.args:
        try:
            args.append(ast.literal_eval(arg))
        except ValueError:
            args.append(ast.unparse(arg))
    return name, args


def _goal_text(obs: dict[str, Any]) -> str:
    goal = obs.get("goal")
    if isinstance(goal, str) and goal.strip():
        return goal.strip()

    parts: list[str] = []
    for message in obs.get("goal_object") or []:
        if isinstance(message, dict) and message.get("type") == "text":
            parts.append(str(message.get("text") or ""))
    return " ".join(part.strip() for part in parts if part.strip())


def _title(obs: dict[str, Any]) -> str:
    titles = obs.get("open_pages_titles") or []
    index = obs.get("active_page_index")
    try:
        active_index = int(index[0]) if index is not None else 0
    except (TypeError, ValueError, IndexError):
        active_index = 0
    if 0 <= active_index < len(titles):
        return str(titles[active_index])
    return ""


def _node_value(node: dict[str, Any], key: str) -> str:
    value = node.get(key)
    if isinstance(value, dict):
        return str(value.get("value") or "")
    return str(value or "")


def _property_map(node: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for prop in node.get("properties") or []:
        if not isinstance(prop, dict):
            continue
        prop_value = prop.get("value") or {}
        if isinstance(prop_value, dict) and "value" in prop_value:
            out[str(prop.get("name"))] = prop_value.get("value")
    return out


def _bool_prop(node: dict[str, Any], key: str) -> bool | None:
    value = _property_map(node).get(key)
    if isinstance(value, bool):
        return value
    if value in {"true", "false"}:
        return value == "true"
    return None


def _bbox_from_extra(extra: dict[str, Any] | None) -> BoundingBox | None:
    if not extra:
        return None
    box = extra.get("bbox")
    if not isinstance(box, list | tuple) or len(box) != 4:
        return None
    return BoundingBox(x=float(box[0]), y=float(box[1]), width=float(box[2]), height=float(box[3]))
