from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_extract_demo_actions_groups_keyboard_text_by_stable_target():
    importer = _load_script("import_miniwob_demos")
    demo = {
        "states": [
            _state(None, ""),
            _state({"type": "keydown", "keyCode": 87, "charCode": 0, "timing": 1}, ""),
            _state({"type": "keydown", "keyCode": 87, "charCode": 0, "timing": 3}, ""),
            _state({"type": "keypress", "keyCode": 87, "charCode": 87, "timing": 1}, ""),
            _state({"type": "keypress", "keyCode": 87, "charCode": 87, "timing": 3}, ""),
            _state({"type": "keyup", "keyCode": 87, "charCode": 0, "timing": 1}, "W"),
            _state({"type": "keyup", "keyCode": 87, "charCode": 0, "timing": 3}, "W"),
            _state({"type": "keydown", "keyCode": 65, "charCode": 0, "timing": 1}, "W"),
            _state({"type": "keydown", "keyCode": 65, "charCode": 0, "timing": 3}, "W"),
            _state({"type": "keypress", "keyCode": 97, "charCode": 97, "timing": 1}, "W"),
            _state({"type": "keypress", "keyCode": 97, "charCode": 97, "timing": 3}, "W"),
            _state({"type": "keyup", "keyCode": 65, "charCode": 0, "timing": 1}, "Wa"),
            _state({"type": "keyup", "keyCode": 65, "charCode": 0, "timing": 3}, "Wa"),
        ]
    }

    actions = importer.extract_demo_actions(demo)

    assert len(actions) == 1
    assert actions[0].action.type == "type"
    assert actions[0].action.target == "field"
    assert actions[0].action.text == "Wa"


def _state(action: dict | None, value: str) -> dict:
    return {
        "action": action,
        "dom": {
            "tag": "BODY",
            "children": [
                {
                    "tag": "INPUT_text",
                    "id": "field",
                    "ref": 7,
                    "left": 10,
                    "top": 20,
                    "width": 80,
                    "height": 20,
                    "value": value,
                    "focused": True,
                    "recordingTarget": True,
                    "children": [],
                }
            ],
        },
    }


def _load_script(name: str):
    repo_root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(name, repo_root / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
