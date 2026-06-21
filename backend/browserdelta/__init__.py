"""BrowserDelta backend package."""

from typing import TYPE_CHECKING

__all__ = ["__version__", "BrowserDeltaSession", "record_task"]

__version__ = "0.1.0"

if TYPE_CHECKING:
    from browserdelta.sdk import BrowserDeltaSession, record_task


def __getattr__(name: str):
    # Lazily expose the SDK so `import browserdelta` stays light (no Playwright
    # import) for API/codec consumers, while `browserdelta.BrowserDeltaSession`
    # still works for agent integrations.
    if name in {"BrowserDeltaSession", "record_task"}:
        from browserdelta import sdk

        return getattr(sdk, name)
    raise AttributeError(f"module 'browserdelta' has no attribute {name!r}")
