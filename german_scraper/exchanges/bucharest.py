"""Bucharest Stock Exchange (BVB) pre & post-trade scraper."""
from __future__ import annotations

import re

from playwright.async_api import Page

from .base import Exchange
from german_scraper.core.throttle import random_delay

MAIN_URL: str = "https://www.bvb.ro/TradingAndStatistics/Trading/MiFIDIIData"


class Bucharest(Exchange):
    """Bucharest Stock Exchange (BVB) MiFID II data."""

    name: str = "Bucharest Stock Exchange (BVB)"

    async def _dismiss_popups(self, page: Page) -> None:
        for label in ("Accept", "OK", "Close", "Got it", "Agree"):
            try:
                btn = page.get_by_role("button", name=re.compile(f"^{label}$", re.I))
                if await btn.is_visible():
                    self.logger.info("Dismissing popup '%s'", label)
                    await btn.click()
                    await page.wait_for_timeout(400)
            except Exception:
                continue

    async def _try_quick_download(
        self,
        page: Page,
        link_pattern: str,
        subdir: str,
        label: str,
    ) -> None:
        link = page.get_by_role("link", name=re.compile(link_pattern, re.I))
        if not await link.is_visible():
            self.logger.error("Bucharest link not visible: %s", label)
            return
        await self._download_via_click(page, link, subdir, label, post_delay=(1.0, 2.0))

    async def run(self) -> None:
        """Download Pre-Trade quick file plus Current and Previous post-trade files."""
        page = await self.browser.new_page()
        try:
            await page.goto(MAIN_URL)
            await self._dismiss_popups(page)

            en_button = page.get_by_text("EN", exact=True)
            if await en_button.is_visible():
                await en_button.click()
                self.logger.info("Switched site to English")
                await random_delay(1, 2)

            await self._try_quick_download(
                page, r"^Quick download$", "bucharest/Pre", "Pre-Trade-Quick-Download",
            )

            post_link = page.get_by_role("link", name=re.compile(r"Post - Trade", re.I))
            if not await post_link.is_visible():
                self.logger.error("Bucharest Post-Trade page link not found")
                return
            await post_link.click()
            self.logger.info("Moved to Post-Trade section")
            await self._dismiss_popups(page)

            await self._try_quick_download(
                page, r"Quick download - Current", "bucharest/Post",
                "Post-Trade-Quick-Download-Current",
            )
            await self._try_quick_download(
                page, r"Quick download - Previous", "bucharest/Post",
                "Post-Trade-Quick-Download-Previous",
            )
            self.logger.info("All Bucharest files handled")
        finally:
            await page.close()
