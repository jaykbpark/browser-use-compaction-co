#!/usr/bin/env python3
"""Record a raw BrowserDelta run from a task file under tasks/."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from browserdelta.browserbase.recorder import StepRecorder  # noqa: E402
from browserdelta.browserbase.session import open_page  # noqa: E402
from browserdelta.schemas import BrowserAction  # noqa: E402


async def record_task(task: dict, headless: bool = True) -> str:
    run_id = task["id"]
    start_url = task["start_url"]
    actions = [BrowserAction.model_validate(action) for action in task["actions"]]

    async with open_page(headless=headless) as (page, mode):
        await page.goto(start_url, wait_until="domcontentloaded")
        recorder = StepRecorder(run_id=run_id, start_url=start_url, mode=mode)
        for action in actions:
            record = await recorder.record_action(page, action)
            print(f"step {record.step}: {record.action.type} -> {record.result.ok}")
    print(f"wrote runs/{run_id}")
    return run_id


async def main() -> None:
    parser = argparse.ArgumentParser(description="Record a BrowserDelta run from a task file.")
    parser.add_argument("task_path", type=Path)
    parser.add_argument("--headed", action="store_true", help="Run with a visible browser window.")
    args = parser.parse_args()

    task = json.loads(args.task_path.read_text())
    await record_task(task, headless=not args.headed)


if __name__ == "__main__":
    asyncio.run(main())
