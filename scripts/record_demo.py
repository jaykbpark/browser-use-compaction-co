#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from browserdelta.browserbase.recorder import StepRecorder  # noqa: E402
from browserdelta.browserbase.session import open_page  # noqa: E402
from browserdelta.compaction.codec import compact_run  # noqa: E402
from browserdelta.schemas import BrowserAction  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Record a raw BrowserDelta run.")
    parser.add_argument("--task", type=Path, help="Task JSON with start_url and actions.")
    parser.add_argument("--url", help="Override the task start URL.")
    parser.add_argument("--run-id", help="Run folder name. Defaults to task id or smoke.")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--compact", action="store_true", help="Compact the recorded run immediately."
    )
    parser.add_argument(
        "--runtime",
        choices=["auto", "local", "browserbase"],
        default="auto",
        help="Browser runtime. auto uses Browserbase when credentials are set.",
    )
    args = parser.parse_args()

    task = load_task(args.task)
    start_target = args.url or task["start_url"]
    run_id = args.run_id or task["id"]
    actions = [BrowserAction.model_validate(action) for action in task["actions"]]

    async with open_page(headless=args.headless, runtime=args.runtime) as (page, mode):
        start_url = await open_start_page(page, start_target, mode)
        recorder = StepRecorder(
            run_id=run_id,
            start_url=start_url,
            mode=mode,
            metadata={
                "goal": task.get("goal", ""),
                "success_hint": task.get("success_hint", ""),
                "task_id": task.get("id", ""),
            },
        )
        run_path = recorder.path

        for action in actions:
            record = await recorder.record_action(page, action)
            print(f"step {record.step}: {record.action.type} -> {record.result.ok}")

    print(f"wrote {display_path(run_path)}")

    if args.compact:
        observations = compact_run(run_path)
        for observation in observations:
            print(
                f"compact step {observation.step}: {observation.route}, "
                f"{observation.reduction_pct:.2f}% saved - {observation.summary}"
            )


def load_task(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "id": "smoke",
            "start_url": "https://example.com",
            "actions": [
                {"type": "wait", "amount": 500},
                {"type": "press", "key": "Tab"},
                {"type": "press", "key": "Enter"},
            ],
        }

    task_path = path if path.is_absolute() else ROOT / path
    data = json.loads(task_path.read_text())
    if "id" not in data:
        data["id"] = task_path.stem
    if "start_url" not in data:
        raise ValueError(f"{task_path} is missing start_url")
    if "actions" not in data:
        raise ValueError(f"{task_path} is missing actions")
    return data


def resolve_start_url(value: str) -> str:
    if value.startswith(("http://", "https://", "file://", "data:", "about:")):
        return value

    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    if candidate.exists():
        return candidate.resolve().as_uri()

    return value


async def open_start_page(page, value: str, mode: str) -> str:
    local_path = _local_file_path(value)
    if local_path and mode == "browserbase":
        await page.set_content(local_path.read_text(), wait_until="domcontentloaded")
        return local_path.as_uri()

    start_url = resolve_start_url(value)
    await page.goto(start_url, wait_until="domcontentloaded")
    return start_url


def _local_file_path(value: str) -> Path | None:
    if value.startswith("file://"):
        parsed = urlparse(value)
        candidate = Path(unquote(parsed.path))
        return candidate if candidate.exists() else None
    if value.startswith(("http://", "https://", "data:", "about:")):
        return None

    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    return candidate.resolve() if candidate.exists() else None


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    asyncio.run(main())
