#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from browserdelta.compaction.codec import compact_run  # noqa: E402
from browserdelta.schemas import (  # noqa: E402
    ActionResult,
    BoundingBox,
    BrowserAction,
    InteractiveElement,
    PageState,
    RunManifest,
    StatePointer,
    StepRecord,
)
from browserdelta.storage import run_dir, write_json, write_manifest, write_steps  # noqa: E402


KEY_NAMES = {
    9: "Tab",
    13: "Enter",
    27: "Escape",
}


@dataclass
class ImportedRun:
    run_id: str
    run_path: Path
    task_name: str
    demo_path: Path
    action_count: int
    goal: str


@dataclass
class DemoAction:
    action: BrowserAction
    before_index: int
    after_index: int


@dataclass
class KeyGroup:
    target: dict[str, Any] | None
    before_index: int
    after_index: int
    text: str = ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import successful MiniWoB++ human demonstrations as BrowserDelta runs."
    )
    parser.add_argument("demos_root", type=Path)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--prefix", default="miniwob_demo")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--suite-out", type=Path)
    parser.add_argument("--min-actions", type=int, default=2)
    parser.add_argument(
        "--max-per-task",
        type=int,
        default=0,
        help="Optional cap per MiniWoB task. 0 means no cap.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    selected = select_demo_paths(
        args.demos_root,
        limit=args.limit,
        min_actions=args.min_actions,
        max_per_task=args.max_per_task or None,
    )
    imported = [
        import_demo(path, run_id=f"{args.prefix}_{index:03d}", compact=args.compact)
        for index, path in enumerate(selected, start=1)
    ]

    suite = {
        "suite": f"{args.prefix}_miniwob_demos",
        "runs": [
            {"path": str(run.run_path), "goal": run.goal}
            for run in imported
        ],
    }
    if args.suite_out:
        args.suite_out.parent.mkdir(parents=True, exist_ok=True)
        args.suite_out.write_text(json.dumps(suite, indent=2) + "\n")

    payload = {
        "imported": len(imported),
        "unique_tasks": len({run.task_name for run in imported}),
        "runs": [
            {
                "run_id": run.run_id,
                "task_name": run.task_name,
                "action_count": run.action_count,
                "demo_path": str(run.demo_path),
            }
            for run in imported
        ],
        "suite_path": str(args.suite_out) if args.suite_out else None,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"imported={payload['imported']} unique_tasks={payload['unique_tasks']} "
            f"suite={payload['suite_path'] or '(not written)'}"
        )
    return 0


def select_demo_paths(
    demos_root: Path,
    *,
    limit: int,
    min_actions: int,
    max_per_task: int | None = None,
) -> list[Path]:
    by_task: dict[str, deque[Path]] = defaultdict(deque)
    for path in sorted(demos_root.rglob("*.json.gz")):
        data = _load_demo(path)
        if int(data.get("rawReward") or 0) != 1:
            continue
        actions = extract_demo_actions(data)
        if len(actions) < min_actions:
            continue
        by_task[_task_name(path, data)].append(path)

    selected: list[Path] = []
    per_task_counts: dict[str, int] = defaultdict(int)
    task_names = sorted(by_task)
    while len(selected) < limit:
        progressed = False
        for task_name in task_names:
            if len(selected) >= limit:
                break
            if max_per_task is not None and per_task_counts[task_name] >= max_per_task:
                continue
            if not by_task[task_name]:
                continue
            selected.append(by_task[task_name].popleft())
            per_task_counts[task_name] += 1
            progressed = True
        if not progressed:
            break

    if len(selected) < limit:
        raise RuntimeError(
            f"Only found {len(selected)} successful demos with at least {min_actions} actions."
        )
    return selected


def import_demo(path: Path, *, run_id: str, compact: bool) -> ImportedRun:
    data = _load_demo(path)
    states = data.get("states") or []
    actions = extract_demo_actions(data)
    task_name = _task_name(path, data)
    goal = str(data.get("utterance") or "")

    run_path = run_dir(run_id)
    if run_path.exists():
        shutil.rmtree(run_path)
    run_path = run_dir(run_id)

    write_manifest(
        run_path,
        RunManifest(
            run_id=run_id,
            start_url=f"miniwob-demo://{task_name}",
            mode="local",
            metadata={
                "source": "miniwob-plusplus-demos",
                "task_name": task_name,
                "goal": goal,
                "demo_path": str(path),
                "rawReward": data.get("rawReward"),
                "reward": data.get("reward"),
            },
        ),
    )

    steps: list[StepRecord] = []
    for step_number, demo_action in enumerate(actions, start=1):
        before = _write_state(
            run_path,
            step_number,
            "before",
            states[demo_action.before_index],
            task_name=task_name,
            goal=goal,
        )
        after = _write_state(
            run_path,
            step_number,
            "after",
            states[demo_action.after_index],
            task_name=task_name,
            goal=goal,
        )
        steps.append(
            StepRecord(
                step=step_number,
                action=demo_action.action,
                result=ActionResult(ok=True),
                before=before,
                after=after,
            )
        )
    write_steps(run_path, steps)

    if compact:
        compact_run(run_path)

    return ImportedRun(
        run_id=run_id,
        run_path=run_path,
        task_name=task_name,
        demo_path=path,
        action_count=len(actions),
        goal=goal,
    )


def extract_demo_actions(data: dict[str, Any]) -> list[DemoAction]:
    states = data.get("states") or []
    actions: list[DemoAction] = []
    key_group: KeyGroup | None = None

    def flush_key_group() -> None:
        nonlocal key_group
        if key_group and key_group.text:
            actions.append(
                DemoAction(
                    action=BrowserAction(
                        type="type",
                        target=_target_label(key_group.target),
                        text=key_group.text,
                        metadata={"source": "miniwob-demo"},
                    ),
                    before_index=key_group.before_index,
                    after_index=key_group.after_index,
                )
            )
        key_group = None

    for index, state in enumerate(states):
        event = state.get("action") or {}
        if event.get("timing") != 3:
            continue
        event_type = str(event.get("type") or "")
        target = _event_target(state, event, prefer_focused=event_type.startswith("key"))

        if event_type == "keypress" and int(event.get("charCode") or 0) > 0:
            char = chr(int(event["charCode"]))
            target_key = _target_key(target)
            current_key = _target_key(key_group.target) if key_group else None
            if key_group is None or target_key != current_key:
                flush_key_group()
                key_group = KeyGroup(
                    target=target,
                    before_index=max(0, index - 1),
                    after_index=index,
                )
            key_group.text += char
            key_group.after_index = index
            continue

        if event_type == "keyup" and key_group is not None:
            target_key = _target_key(target)
            if not target_key or target_key == _target_key(key_group.target):
                key_group.after_index = index
            continue

        if event_type == "keydown" and int(event.get("keyCode") or 0) in KEY_NAMES:
            flush_key_group()
            actions.append(
                DemoAction(
                    action=BrowserAction(
                        type="press",
                        target=_target_label(target),
                        key=KEY_NAMES[int(event["keyCode"])],
                        metadata={"source": "miniwob-demo"},
                    ),
                    before_index=max(0, index - 1),
                    after_index=index,
                )
            )
            continue

        if event_type == "click":
            flush_key_group()
            actions.append(
                DemoAction(
                    action=BrowserAction(
                        type="click",
                        target=_target_label(target),
                        metadata={"source": "miniwob-demo"},
                    ),
                    before_index=max(0, index - 1),
                    after_index=index,
                )
            )
            continue

        if event_type not in {"mousedown", "mouseup", "keydown", "keyup", "keypress"}:
            flush_key_group()

    flush_key_group()
    return actions


def _write_state(
    run_path: Path,
    step: int,
    when: str,
    state: dict[str, Any],
    *,
    task_name: str,
    goal: str,
) -> StatePointer:
    screenshot_rel = f"steps/step_{step:03d}_{when}.png"
    state_rel = f"steps/step_{step:03d}_{when}.json"
    screenshot_path = run_path / screenshot_rel
    _write_blank_screenshot(screenshot_path)
    write_json(
        run_path / state_rel,
        _page_state_from_dom(
            state.get("dom") or {},
            screenshot=screenshot_rel,
            task_name=task_name,
            goal=goal,
        ),
    )
    return StatePointer(screenshot=screenshot_rel, state=state_rel)


def _page_state_from_dom(
    dom: dict[str, Any],
    *,
    screenshot: str,
    task_name: str,
    goal: str,
) -> PageState:
    text: list[str] = []
    interactive: list[InteractiveElement] = []
    focused_ref: str | None = None

    for node in _walk_dom(dom):
        node_text = _node_text(node)
        if node_text:
            text.append(node_text)
        element = _interactive_element(node)
        if element:
            interactive.append(element)
        if node.get("focused"):
            focused_ref = _node_ref(node)

    return PageState(
        url=f"miniwob-demo://{task_name}",
        title=task_name,
        text=_dedupe(text)[:200],
        interactive=interactive[:200],
        focused_ref=focused_ref,
        screenshot=screenshot,
        metadata={"source": "miniwob-plusplus-demos", "goal": goal},
    )


def _interactive_element(node: dict[str, Any]) -> InteractiveElement | None:
    role = _role(node)
    if not role:
        return None
    ref = _node_ref(node)
    if not ref:
        return None
    name = _element_name(node)
    return InteractiveElement(
        ref=ref,
        role=role,
        name=name,
        value=str(node.get("value")) if node.get("value") is not None else None,
        checked=_optional_bool(node.get("checked")),
        selected=_optional_bool(node.get("selected")),
        disabled=_optional_bool(node.get("disabled")),
        bbox=BoundingBox(
            x=float(node.get("left") or 0),
            y=float(node.get("top") or 0),
            width=float(node.get("width") or 0),
            height=float(node.get("height") or 0),
        ),
        attributes={
            "id": node.get("id") or "",
            "classes": node.get("classes") or "",
            "tag": node.get("tag") or "",
            "recordingTarget": bool(node.get("recordingTarget")),
        },
    )


def _role(node: dict[str, Any]) -> str:
    tag = str(node.get("tag") or "").upper()
    if tag == "BUTTON" or tag == "INPUT_SUBMIT":
        return "button"
    if tag == "A":
        return "link"
    if tag in {"INPUT_TEXT", "INPUT_PASSWORD", "TEXTAREA"}:
        return "textbox"
    if tag == "INPUT_CHECKBOX":
        return "checkbox"
    if tag == "INPUT_RADIO":
        return "radio"
    if tag == "SELECT":
        return "combobox"
    if tag == "OPTION":
        return "option"
    return ""


def _element_name(node: dict[str, Any]) -> str:
    role = _role(node)
    if role == "textbox":
        return (
            str(node.get("id") or "")
            or str(node.get("classes") or "")
            or _node_text(node)
            or _node_ref(node)
        )
    return (
        _node_text(node)
        or str(node.get("value") or "")
        or str(node.get("id") or "")
        or str(node.get("classes") or "")
        or _node_ref(node)
    )


def _target_label(node: dict[str, Any] | None) -> str:
    if not node:
        return ""
    return _element_name(node)


def _target_key(node: dict[str, Any] | None) -> str:
    if not node:
        return ""
    stable_id = str(node.get("id") or "")
    if stable_id:
        return f"id:{stable_id}"
    return ":".join(
        [
            str(node.get("tag") or ""),
            str(round(float(node.get("left") or 0), 1)),
            str(round(float(node.get("top") or 0), 1)),
            str(round(float(node.get("width") or 0), 1)),
            str(round(float(node.get("height") or 0), 1)),
        ]
    )


def _event_target(
    state: dict[str, Any],
    event: dict[str, Any],
    *,
    prefer_focused: bool = False,
) -> dict[str, Any] | None:
    dom = state.get("dom") or {}
    recording = _recording_target(dom)
    if recording and _target_label(recording):
        return recording

    if prefer_focused:
        focused = _focused_target(dom)
        if focused and _target_label(focused):
            return focused

    coordinate = _coordinate_target(dom, event)
    if coordinate and _target_label(coordinate):
        return coordinate

    if not prefer_focused:
        focused = _focused_target(dom)
        if focused and _target_label(focused):
            return focused

    return recording


def _recording_target(dom: dict[str, Any]) -> dict[str, Any] | None:
    for node in _walk_dom(dom):
        if node.get("recordingTarget"):
            return node
    return None


def _focused_target(dom: dict[str, Any]) -> dict[str, Any] | None:
    for node in _walk_dom(dom):
        if node.get("focused"):
            return node
    return None


def _coordinate_target(dom: dict[str, Any], event: dict[str, Any]) -> dict[str, Any] | None:
    point = _event_point(event)
    if point is None:
        return None
    x, y = point

    containing: list[tuple[float, int, dict[str, Any]]] = []
    nearest: list[tuple[float, float, int, dict[str, Any]]] = []
    for depth, node in _walk_dom_with_depth(dom):
        box = _node_box(node)
        if box is None or not _has_target_signal(node):
            continue
        left, top, width, height = box
        area = max(width * height, 1.0)
        if left <= x <= left + width and top <= y <= top + height:
            containing.append((area, -depth, node))
            continue
        distance = _distance_to_box(x, y, left, top, width, height)
        nearest.append((distance, area, -depth, node))

    if containing:
        _, _, node = sorted(containing, key=lambda item: item[:2])[0]
        return node
    if nearest:
        distance, _, _, node = sorted(nearest, key=lambda item: item[:3])[0]
        if distance <= 24:
            return node
    return None


def _event_point(event: dict[str, Any]) -> tuple[float, float] | None:
    x = event.get("x", event.get("cx"))
    y = event.get("y", event.get("cy"))
    if x is None or y is None:
        return None
    try:
        return float(x), float(y)
    except (TypeError, ValueError):
        return None


def _node_box(node: dict[str, Any]) -> tuple[float, float, float, float] | None:
    try:
        left = float(node.get("left"))
        top = float(node.get("top"))
        width = float(node.get("width"))
        height = float(node.get("height"))
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return left, top, width, height


def _distance_to_box(
    x: float,
    y: float,
    left: float,
    top: float,
    width: float,
    height: float,
) -> float:
    dx = max(left - x, 0.0, x - (left + width))
    dy = max(top - y, 0.0, y - (top + height))
    return (dx * dx + dy * dy) ** 0.5


def _has_target_signal(node: dict[str, Any]) -> bool:
    return bool(
        _node_ref(node)
        or _node_text(node)
        or node.get("id")
        or node.get("classes")
        or node.get("value")
    )


def _walk_dom_with_depth(node: dict[str, Any], depth: int = 0):
    yield depth, node
    for child in node.get("children") or []:
        if isinstance(child, dict):
            yield from _walk_dom_with_depth(child, depth + 1)


def _node_ref(node: dict[str, Any] | None) -> str:
    if not node:
        return ""
    ref = node.get("ref")
    if ref is None or int(ref) < 0:
        return ""
    return str(ref)


def _node_text(node: dict[str, Any]) -> str:
    text = str(node.get("text") or "").strip()
    if text:
        return " ".join(text.split())
    return ""


def _walk_dom(node: dict[str, Any]):
    yield node
    for child in node.get("children") or []:
        if isinstance(child, dict):
            yield from _walk_dom(child)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        normalized = " ".join(value.split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _write_blank_screenshot(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    Image.new("RGB", (800, 600), color=(255, 255, 255)).save(path)


def _load_demo(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Demo is not a JSON object: {path}")
    return data


def _task_name(path: Path, data: dict[str, Any]) -> str:
    return str(data.get("taskName") or path.parent.name)


if __name__ == "__main__":
    raise SystemExit(main())
