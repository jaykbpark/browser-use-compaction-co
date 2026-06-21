"""Programmatic API for using BrowserDelta as a drop-in context compressor.

A browser agent normally re-sends a full screenshot (and/or the whole DOM) to its
LLM after every action. BrowserDelta replaces that with a compact, mostly-text
observation of *what changed*, falling back to cropped regions or a full
screenshot only when the change can't be explained in text.

Live usage (one observation per action):

    from playwright.async_api import async_playwright
    from browserdelta.sdk import BrowserDeltaSession

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://example.com")

        session = BrowserDeltaSession(run_id="flights", start_url=page.url)
        obs = await session.observe(page, {"type": "click", "target": "Search"})
        # feed obs.llm_observation (+ obs.crop_paths) to your model instead of a
        # fresh screenshot every step.

Batch usage (replay a scripted task):

    from browserdelta.sdk import record_task
    run_path, observations = await record_task(task, run_id="flights")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlparse

from playwright.async_api import Page

from browserdelta.browserbase.recorder import StepRecorder
from browserdelta.browserbase.session import open_page
from browserdelta.compaction.codec import compact_step
from browserdelta.schemas import BrowserAction, CompactObservation
from browserdelta.storage import append_jsonl

ActionLike = BrowserAction | Mapping[str, Any]


class BrowserDeltaSession:
    """Wraps a live browser run and emits one compact observation per action.

    The session owns a run folder under ``RUNS_DIR/<run_id>`` where it persists
    raw before/after screenshots, page state, crops, and the rolling
    ``compact_observations.jsonl`` — so any run can later be replayed, scored, or
    opened in the viewer.
    """

    def __init__(
        self,
        run_id: str,
        start_url: str,
        mode: str = "local",
        reset_existing: bool = True,
        metadata: dict | None = None,
    ) -> None:
        self.recorder = StepRecorder(
            run_id=run_id,
            start_url=start_url,
            mode=mode,
            reset_existing=reset_existing,
            metadata=metadata,
        )
        self.run_id = run_id
        self.path: Path = self.recorder.path
        self.observations: list[CompactObservation] = []

    async def observe(self, page: Page, action: ActionLike) -> CompactObservation:
        """Execute ``action`` on ``page`` and return the compact observation.

        Captures before/after state around the action, diffs it, routes it
        (text / crop / full screenshot), and appends the result to the run's
        ``compact_observations.jsonl``.
        """

        browser_action = _coerce_action(action)
        record = await self.recorder.record_action(page, browser_action)
        observation = compact_step(self.path, record)
        append_jsonl(self.path / "compact_observations.jsonl", observation)
        self.observations.append(observation)
        return observation


async def record_task(
    task: Mapping[str, Any],
    run_id: str | None = None,
    headless: bool = True,
    runtime: str = "auto",
) -> tuple[Path, list[CompactObservation]]:
    """Drive a scripted task end to end and return its compact observations.

    ``task`` needs ``start_url`` and ``actions`` (a list of action dicts). The
    optional ``goal``/``success_hint``/``id`` fields are stored in the run
    manifest for later replay evaluation.
    """

    if "start_url" not in task:
        raise ValueError("task is missing 'start_url'")
    if "actions" not in task:
        raise ValueError("task is missing 'actions'")

    actions: Sequence[ActionLike] = task["actions"]
    resolved_run_id = run_id or task.get("id") or "run"

    async with open_page(headless=headless, runtime=runtime) as (page, mode):
        start_url = await _open_start_page(page, task["start_url"], mode)
        session = BrowserDeltaSession(
            run_id=resolved_run_id,
            start_url=start_url,
            mode=mode,
            metadata={
                "goal": task.get("goal", ""),
                "success_hint": task.get("success_hint", ""),
                "task_id": task.get("id", ""),
            },
        )
        for action in actions:
            await session.observe(page, action)

    return session.path, session.observations


def _coerce_action(action: ActionLike) -> BrowserAction:
    if isinstance(action, BrowserAction):
        return action
    return BrowserAction.model_validate(dict(action))


async def _open_start_page(page: Page, value: str, mode: str) -> str:
    """Navigate to ``value`` (URL or local file) and return the resolved URL."""

    local_path = _local_file_path(value)
    if local_path is not None and mode == "browserbase":
        await page.set_content(local_path.read_text(), wait_until="domcontentloaded")
        return local_path.as_uri()

    start_url = _resolve_start_url(value)
    await page.goto(start_url, wait_until="domcontentloaded")
    return start_url


def _resolve_start_url(value: str) -> str:
    if value.startswith(("http://", "https://", "file://", "data:", "about:")):
        return value
    candidate = Path(value)
    if candidate.exists():
        return candidate.resolve().as_uri()
    return value


def _local_file_path(value: str) -> Path | None:
    if value.startswith("file://"):
        candidate = Path(unquote(urlparse(value).path))
        return candidate if candidate.exists() else None
    if value.startswith(("http://", "https://", "data:", "about:")):
        return None
    candidate = Path(value)
    return candidate.resolve() if candidate.exists() else None
