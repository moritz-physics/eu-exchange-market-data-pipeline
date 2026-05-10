"""Centralised Playwright lifecycle management.

A single ``PlaywrightClient`` launches one Chromium browser and yields it as
an async context manager. Headless mode and viewport are configurable via
environment variables so the same code runs on a developer laptop and on a
headless server.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from playwright.async_api import Browser, async_playwright

from german_scraper.core.logging_config import get_logger

logger = get_logger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class PlaywrightClient:
    """Launch one Chromium instance and share it across all scrapers.

    Configurable via env:
        PLAYWRIGHT_HEADLESS  (default: false locally, recommended true on server)
        PLAYWRIGHT_SLOWMO_MS (default: 0)
    """

    def __init__(self, headless: bool | None = None, slow_mo_ms: int | None = None) -> None:
        self.headless: bool = (
            headless if headless is not None else _env_bool("PLAYWRIGHT_HEADLESS", False)
        )
        self.slow_mo_ms: int = (
            slow_mo_ms if slow_mo_ms is not None
            else int(os.environ.get("PLAYWRIGHT_SLOWMO_MS", "0"))
        )

    @asynccontextmanager
    async def launch(self) -> AsyncIterator[Browser]:
        """Yield a ready-to-use Chromium browser; close it on exit."""
        logger.info(
            "Launching Chromium (headless=%s, slow_mo=%dms)",
            self.headless, self.slow_mo_ms,
        )
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo_ms,
            )
            try:
                yield browser
            finally:
                logger.info("Closing Chromium")
                await browser.close()
