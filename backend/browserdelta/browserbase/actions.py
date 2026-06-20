from __future__ import annotations

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from browserdelta.schemas import ActionResult, BrowserAction


async def execute_action(page: Page, action: BrowserAction) -> ActionResult:
    try:
        match action.type:
            case "goto":
                if not action.url:
                    return ActionResult(ok=False, error="goto action requires url")
                await page.goto(action.url, wait_until="domcontentloaded")
            case "click":
                if not action.target:
                    return ActionResult(ok=False, error="click action requires target")
                await (await _locator_for_target(page, action.target)).click(timeout=5000)
            case "type":
                if not action.target or action.text is None:
                    return ActionResult(ok=False, error="type action requires target and text")
                locator = await _locator_for_target(page, action.target)
                await locator.click(timeout=5000)
                await locator.fill(action.text)
            case "press":
                if not action.key:
                    return ActionResult(ok=False, error="press action requires key")
                await page.keyboard.press(action.key)
            case "scroll":
                amount = action.amount or 600
                await page.mouse.wheel(0, amount)
            case "wait":
                await page.wait_for_timeout(action.amount or 1000)
        await page.wait_for_load_state("domcontentloaded")
        return ActionResult(ok=True, message=f"{action.type} executed")
    except PlaywrightTimeoutError as exc:
        return ActionResult(ok=False, error=f"timeout: {exc}")
    except Exception as exc:  # noqa: BLE001 - runner should log browser failures, not crash
        return ActionResult(ok=False, error=str(exc))


async def _locator_for_target(page: Page, target: str):
    """Resolve a human-ish target. Replace with ref-based lookup once refs are stable."""

    if target.startswith("css="):
        return page.locator(target.removeprefix("css=")).first
    if target.startswith("text="):
        return page.get_by_text(target.removeprefix("text=")).first
    if target.startswith("placeholder="):
        return page.get_by_placeholder(target.removeprefix("placeholder=")).first
    if target.startswith("label="):
        return page.get_by_label(target.removeprefix("label=")).first

    candidates = [
        page.get_by_label(target).first,
        page.get_by_placeholder(target).first,
        page.get_by_role("button", name=target).first,
        page.get_by_role("link", name=target).first,
        page.locator(f'input[value*="{target}" i]').first,
        page.get_by_text(target, exact=False).first,
    ]

    for locator in candidates:
        if await locator.count() > 0:
            return locator

    return page.get_by_text(target, exact=False).first
