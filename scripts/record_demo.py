#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from browserdelta.browserbase.recorder import StepRecorder  # noqa: E402
from browserdelta.browserbase.session import open_page  # noqa: E402
from browserdelta.schemas import BrowserAction  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Record a raw BrowserDelta run.")
    parser.add_argument("--url", default="https://example.com")
    parser.add_argument("--run-id", default="smoke")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    async with open_page(headless=args.headless) as (page, mode):
        await page.goto(args.url, wait_until="domcontentloaded")
        recorder = StepRecorder(run_id=args.run_id, start_url=args.url, mode=mode)

        actions = [
            BrowserAction(type="wait", amount=500),
            BrowserAction(type="press", key="Tab"),
            BrowserAction(type="press", key="Enter"),
        ]

        for action in actions:
            record = await recorder.record_action(page, action)
            print(f"step {record.step}: {record.action.type} -> {record.result.ok}")

    print(f"wrote runs/{args.run_id}")


if __name__ == "__main__":
    asyncio.run(main())
