from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any
from typing import AsyncIterator

from playwright.async_api import Browser, Page, async_playwright

from browserdelta.config import get_settings


@asynccontextmanager
async def open_page(
    headless: bool = True,
    runtime: str = "auto",
) -> AsyncIterator[tuple[Page, str]]:
    """Open a Browserbase page when configured, otherwise a local Chromium page."""

    if runtime not in {"auto", "local", "browserbase"}:
        raise ValueError("runtime must be auto, local, or browserbase")

    settings = get_settings()
    playwright = await async_playwright().start()
    browser: Browser | None = None
    mode = "local"
    try:
        use_browserbase = runtime == "browserbase" or (
            runtime == "auto"
            and bool(settings.browserbase_connect_url or settings.browserbase_api_key)
        )
        if runtime == "browserbase" and not (
            settings.browserbase_connect_url or settings.browserbase_api_key
        ):
            raise RuntimeError(
                "Browserbase runtime requested, but no Browserbase credentials are set."
            )

        if use_browserbase and settings.browserbase_connect_url:
            mode = "browserbase"
            browser = await playwright.chromium.connect_over_cdp(settings.browserbase_connect_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = context.pages[0] if context.pages else await context.new_page()
            await page.set_viewport_size({"width": 1280, "height": 800})
        elif use_browserbase and settings.browserbase_api_key:
            mode = "browserbase"
            session = await asyncio.to_thread(_create_browserbase_session)
            connect_url = _session_connect_url(session)
            browser = await playwright.chromium.connect_over_cdp(connect_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = context.pages[0] if context.pages else await context.new_page()
            await page.set_viewport_size({"width": 1280, "height": 800})
        else:
            browser = await playwright.chromium.launch(headless=headless)
            context = await browser.new_context(viewport={"width": 1280, "height": 800})
            page = await context.new_page()
        yield page, mode
    finally:
        if browser is not None:
            await browser.close()
        await playwright.stop()


def _create_browserbase_session() -> Any:
    settings = get_settings()
    try:
        from browserbase import Browserbase
    except ImportError as exc:  # pragma: no cover - exercised only when dependency is missing
        raise RuntimeError(
            "BROWSERBASE_API_KEY is set, but the browserbase package is not installed. "
            'Run pip install -e ".[dev]".'
        ) from exc

    client = Browserbase(api_key=settings.browserbase_api_key)
    kwargs: dict[str, str] = {}
    if settings.browserbase_project_id:
        kwargs["project_id"] = settings.browserbase_project_id
    return client.sessions.create(**kwargs)


def _session_connect_url(session: Any) -> str:
    connect_url = getattr(session, "connect_url", None) or getattr(session, "connectUrl", None)
    if not connect_url:
        raise RuntimeError("Browserbase session did not include a connect URL.")
    return str(connect_url)
