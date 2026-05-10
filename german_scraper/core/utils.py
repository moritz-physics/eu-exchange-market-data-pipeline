"""Cross-scraper Playwright helpers."""
from __future__ import annotations

import re
from typing import Iterable

from playwright.async_api import Page

from german_scraper.core.logging_config import get_logger
from german_scraper.core.throttle import random_delay  # re-export for back-compat

__all__ = ["click_first_consent", "random_delay"]

logger = get_logger(__name__)

_CONSENT_PATTERNS: tuple[str, ...] = (
    "Accept", "Accept All", "Accept All Cookies", "OK", "Ok", "Weiter",
    "Agree", "Akzeptieren", "Allow all", "I Accept", "Got it",
)


async def click_first_consent(
    page: Page,
    extra_patterns: Iterable[str] = (),
    timeout_ms: int = 5_000,
) -> bool:
    """Click the first visible cookie/consent button found on the page.

    Tries a regex over a curated list of common labels. Returns ``True`` if a
    button was clicked, ``False`` otherwise. Never raises — consent dialogs
    are best-effort and absence is normal once a session has consented.
    """
    patterns = list(_CONSENT_PATTERNS) + list(extra_patterns)
    pattern = re.compile("^(" + "|".join(re.escape(p) for p in patterns) + ")$", re.I)
    try:
        button = page.locator("button", has_text=pattern).first
        await button.wait_for(state="visible", timeout=timeout_ms)
        await button.click()
        logger.info("Clicked consent button")
        return True
    except Exception as exc:
        logger.debug("No consent button clicked (%s)", exc)
        return False
