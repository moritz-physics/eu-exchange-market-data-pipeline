"""Börse Berlin pre & post-trade CSV scraper.

Pre-trade and post-trade pages each list dozens to hundreds of CSV
download anchors. The HTTP fast path is used here — Playwright opens
the page once for cookie consent and to read the anchor list, then each
file streams over plain HTTP. Roughly 10× faster than triggering the
browser's download mechanism per file.

Batching to ``MAX_FILES_PER_RUN`` per invocation and manifest-based
dedupe are preserved.
"""
from __future__ import annotations

import asyncio
import re

from playwright.async_api import Page

from german_scraper.core.http_downloader import collect_anchor_urls
from .base import Exchange
from german_scraper.core.utils import click_first_consent
from german_scraper.settings import SETTINGS

PRE_URL: str = SETTINGS.exchange_url(
    "berlin_pre",
    "https://www.boerse-berlin.com/index.php/MiFid_2_Information/Pretrades",
)
POST_URL: str = SETTINGS.exchange_url(
    "berlin_post",
    "https://www.boerse-berlin.com/index.php/MiFid_2_Information/Post_Trade",
)

_PACING: dict = SETTINGS.pacing("berlin")


class Berlin(Exchange):
    """Boerse Berlin (boerse-berlin.com) – MiFID II delayed data.

    Subclass-style configuration:
        ``max_files_per_run`` – cap on downloads per invocation (default 50).
        ``long_break_sec``    – sleep after hitting the cap. Cron variants
                                set this to 0 so the run exits cleanly.
        ``post_delay``        – ``(min, max)`` seconds between downloads.
                                Bigger values for cron variants to stay polite.
    """

    name: str = "Börse Berlin"
    max_files_per_run: int = int(_PACING["max_files_per_run"])
    long_break_sec: int = int(_PACING["long_break_sec"])
    post_delay: tuple[float, float] = tuple(_PACING["post_delay"])  # type: ignore[assignment]

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
        """Visit ``url`` and HTTP-stream every matching CSV anchor."""
        await page.goto(url)
        await click_first_consent(page)

        if use_type_attr:
            selector: str = "a[type='text/comma-separated-values']"
        elif use_href_csv:
            selector = "a[href$='.csv']"
        else:
            selector = "a"
        await page.wait_for_selector(selector, timeout=15_000)

        anchors = await collect_anchor_urls(page, selector)
        if not (use_type_attr or use_href_csv):
            pattern = re.compile(regex, re.I)
            anchors = [(label, href) for label, href in anchors if pattern.search(label)]

        self.logger.info("%s: %d links on %s", self.name, len(anchors), url)

        downloaded_this_run = 0
        for label, href in anchors:
            if not label:
                continue
            if downloaded_this_run >= self.max_files_per_run:
                self.logger.info("Reached batch limit (%d).", self.max_files_per_run)
                if self.long_break_sec:
                    self.logger.info("Cooling off %ds.", self.long_break_sec)
                    await asyncio.sleep(self.long_break_sec)
                break

            saved = await self._download_via_http(
                page, href, subdir, label, post_delay=self.post_delay,
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
