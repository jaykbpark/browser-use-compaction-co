from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from playwright.async_api import Browser, Page, async_playwright

from browserdelta.config import get_settings


@asynccontextmanager
async def open_page(headless: bool = True) -> AsyncIterator[tuple[Page, str]]:
    """Open a Browserbase page when configured, otherwise a local Chromium page."""

    settings = get_settings()
    playwright = await async_playwright().start()
    browser: Browser | None = None
    mode = "local"
    try:
        if settings.browserbase_connect_url:
            mode = "browserbase"
            browser = await playwright.chromium.connect_over_cdp(settings.browserbase_connect_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = context.pages[0] if context.pages else await context.new_page()
        else:
            browser = await playwright.chromium.launch(headless=headless)
            context = await browser.new_context(viewport={"width": 1280, "height": 800})
            page = await context.new_page()
        yield page, mode
    finally:
        if browser is not None:
            await browser.close()
        await playwright.stop()
