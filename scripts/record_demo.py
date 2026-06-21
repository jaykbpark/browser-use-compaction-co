#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from browserdelta.browserbase.recorder import StepRecorder  # noqa: E402
from browserdelta.browserbase.session import open_page  # noqa: E402
from browserdelta.compaction.codec import compact_run  # noqa: E402
from browserdelta.config import get_settings  # noqa: E402
from browserdelta.schemas import BrowserAction  # noqa: E402
from record_task import record_task  # noqa: E402


async def _record_url(url: str, run_id: str, headless: bool) -> None:
    async with open_page(headless=headless) as (page, mode):
        await page.goto(url, wait_until="domcontentloaded")
        recorder = StepRecorder(run_id=run_id, start_url=url, mode=mode)
        actions = [
            BrowserAction(type="wait", amount=500),
            BrowserAction(type="press", key="Tab"),
            BrowserAction(type="press", key="Enter"),
        ]
        for action in actions:
            record = await recorder.record_action(page, action)
            print(f"step {record.step}: {record.action.type} -> {record.result.ok}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Record a raw BrowserDelta run.")
    parser.add_argument("--task", type=Path, default=None, help="Task JSON file to record.")
    parser.add_argument(
        "--url", default="https://example.com", help="URL for the built-in demo script."
    )
    parser.add_argument(
        "--run-id", default=None, help="Run id (defaults to the task id, or 'smoke')."
    )
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--compact", action="store_true", help="Compact the run after recording.")
    parser.add_argument(
        "--runtime",
        choices=["local", "browserbase"],
        default="local",
        help="Browser runtime. 'browserbase' requires BROWSERBASE_CONNECT_URL.",
    )
    args = parser.parse_args()

    if args.runtime == "browserbase" and not get_settings().browserbase_connect_url:
        parser.error("--runtime browserbase requires BROWSERBASE_CONNECT_URL in the environment")

    if args.task is not None:
        task = json.loads(args.task.read_text())
        if args.run_id:
            task["id"] = args.run_id
        run_id = await record_task(task, headless=args.headless)
    else:
        run_id = args.run_id or "smoke"
        await _record_url(args.url, run_id, args.headless)

    if args.compact:
        run_path = get_settings().runs_dir / run_id
        observations = compact_run(run_path)
        print(f"compacted {len(observations)} steps -> {run_path / 'compact_observations.jsonl'}")

    print(f"wrote runs/{run_id}")


if __name__ == "__main__":
    asyncio.run(main())
