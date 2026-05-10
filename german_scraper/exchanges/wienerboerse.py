"""Wiener Börse pre-trade ZIP scraper.

The Wiener Börse prices page exposes its download via a global JS
``onClick()`` function rather than an anchor href, so we wait for the
function to be defined and invoke it directly.
"""
from __future__ import annotations

import asyncio
import random

from playwright.async_api import Page, TimeoutError

from .base import Exchange
from german_scraper.core.throttle import random_delay

URLS: list[tuple[str, str]] = [
    ("Prices Tab 2", "https://prices.wienerborse.at/#tab-content2"),
    ("Prices Tab 3", "https://prices.wienerborse.at/#tab-content3"),
    ("Prices Tab 4", "https://prices.wienerborse.at/#tab-content4"),
]

MAX_RELOADS_PER_TAB: int = 1
ONCLICK_WAIT_MS: int = 15_000


class WienerBoerse(Exchange):
    """Wiener Börse pre-trade ZIP downloader (no stealth)."""

    name: str = "Wiener Börse"

    async def _trigger_download_via_js(self, page: Page):
        """Invoke the page's ``onClick()`` function and capture the download."""
        try:
            await page.wait_for_function(
                "typeof onClick === 'function'", timeout=ONCLICK_WAIT_MS,
            )
        except TimeoutError:
            return None
        async with page.expect_download() as dl_info:
            await page.evaluate("onClick()")
        return await dl_info.value

    async def run(self) -> None:
        """Iterate the three configured price tabs and trigger each download."""
        page = await self.browser.new_page()
        try:
            for tab_name, url in URLS:
                self.logger.info("Navigating to %s (%s)", url, tab_name)
                reloads_left = MAX_RELOADS_PER_TAB

                while True:
                    await page.goto(url)
                    wait_time = random.uniform(5, 8)
                    self.logger.info("Waiting %.1fs for JS to load", wait_time)
                    await asyncio.sleep(wait_time)

                    download = await self._trigger_download_via_js(page)
                    if download:
                        filename = download.suggested_filename
                        label = f"{tab_name}: {filename}"
                        if self.debug:
                            self.logger.info("(DEBUG) Would download %s", label)
                        elif self.pipeline.has_seen(label):
                            self.logger.info("(SKIP) Already have %s", label)
                        else:
                            self.logger.info("Saving %s", label)
                            await self.pipeline.save(download, "wienerboerse")
                        await random_delay(2, 4)
                        break

                    if reloads_left:
                        reloads_left -= 1
                        extra_wait = random.uniform(5, 7)
                        self.logger.warning(
                            "Reloading once (JS not ready). Waiting %.1fs", extra_wait,
                        )
                        await asyncio.sleep(extra_wait)
                        continue
                    self.logger.error("Gave up on %s — onClick() never appeared", tab_name)
                    break
        finally:
            await page.close()
