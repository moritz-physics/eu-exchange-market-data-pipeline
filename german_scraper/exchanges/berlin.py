"""Börse Berlin pre & post-trade CSV scraper.

Pre-trade and post-trade pages each list dozens to hundreds of CSV download
anchors. This scraper batches downloads to ``MAX_FILES_PER_RUN`` per
invocation and respects the manifest dedupe so subsequent runs only fetch
new files.
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional

from playwright.async_api import Page

from .base import Exchange
from german_scraper.core.throttle import random_delay
from german_scraper.core.utils import click_first_consent

PRE_URL: str = "https://www.boerse-berlin.com/index.php/MiFid_2_Information/Pretrades"
POST_URL: str = "https://www.boerse-berlin.com/index.php/MiFid_2_Information/Post_Trade"

MAX_FILES_PER_RUN: int = 50
LONG_BREAK_SEC: int = 30


class Berlin(Exchange):
    """Boerse Berlin (boerse-berlin.com) – MiFID II delayed data."""

    name: str = "Börse Berlin"

    async def _process(
        self,
        page: Page,
        url: str,
        regex: str,
        subdir: str,
        *,
        use_href_csv: bool = False,
        use_type_attr: bool = False,
    ) -> None:
        """Visit ``url`` and download every matching CSV anchor."""
        await page.goto(url)
        await click_first_consent(page)

        if use_type_attr:
            selector: str = "a[type='text/comma-separated-values']"
        elif use_href_csv:
            selector = "a[href$='.csv']"
        else:
            selector = "a"
        await page.wait_for_selector(selector, timeout=15_000)

        if use_type_attr or use_href_csv:
            links = await page.locator(selector).all()
        else:
            links = await page.locator("a").filter(has_text=re.compile(regex, re.I)).all()

        self.logger.info("%s: %d links on %s", self.name, len(links), url)

        downloaded_this_run = 0
        for i, link in enumerate(links, 1):
            text: Optional[str] = await link.text_content()
            label = (text or "").strip()
            if not label:
                continue

            if downloaded_this_run >= MAX_FILES_PER_RUN:
                self.logger.warning("Reached batch limit (%d). Cooling off %ds.",
                                    MAX_FILES_PER_RUN, LONG_BREAK_SEC)
                if LONG_BREAK_SEC:
                    await asyncio.sleep(LONG_BREAK_SEC)
                break

            saved = await self._download_via_click(
                page, link, subdir, label, post_delay=(0.2, 0.6),
            )
            if saved:
                downloaded_this_run += 1

    async def run(self) -> None:
        """Scrape the pre-trade page, then the post-trade page."""
        page = await self.browser.new_page()
        try:
            await self._process(
                page, PRE_URL,
                r"^Download der Pretrade Daten für ",
                "berlin/pretrade",
            )
            await self._process(
                page, POST_URL,
                r"", "berlin/posttrade",
                use_type_attr=True,
            )
        finally:
            await page.close()
