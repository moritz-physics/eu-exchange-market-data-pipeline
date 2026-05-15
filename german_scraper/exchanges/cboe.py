"""Cboe Europe equities trade-data scraper.

Downloads the per-market hourly RTS-13 public trade data CSVs across the
four Cboe markets: BXE, CXE, DXE, APA.

Uses the HTTP fast path: Playwright opens the page only to accept
cookies and read the anchor list; the actual files stream over plain
HTTP with cookies copied from the browser context. About 10× faster
than ``page.expect_download()`` and frees the browser for other work.
"""
from __future__ import annotations

import asyncio
import re

from playwright.async_api import Page

from german_scraper.core.http_downloader import collect_anchor_urls
from german_scraper.settings import SETTINGS
from .base import Exchange

CBOE_URL: str = SETTINGS.exchange_url(
    "cboe", "https://www.cboe.com/europe/equities/trade_data/"
)
MARKETS: tuple[str, ...] = ("bxe", "cxe", "dxe", "apa")


class Cboe(Exchange):
    """Cboe Europe hourly trade-data CSV scraper."""

    name: str = "Cboe Europe"

    async def _dismiss_cookie_banner(self, page: Page, timeout_s: int = 5) -> None:
        """Wait briefly for the OneTrust 'Accept All' button and click it."""
        await asyncio.sleep(2)
        for _ in range(timeout_s * 2):
            try:
                btn = page.get_by_role("button", name=re.compile(r"Accept All", re.I))
                if await btn.is_visible():
                    self.logger.info("Accepting cookies")
                    await btn.click()
                    await page.wait_for_timeout(400)
                    return
            except Exception:
                pass
            await asyncio.sleep(0.5)
        self.logger.debug("Cboe cookie banner not present")

    async def run(self) -> None:
        """Download every hourly CSV across the four Cboe markets."""
        page = await self.browser.new_page()
        try:
            await page.goto(CBOE_URL)
            await self._dismiss_cookie_banner(page)
            self.logger.info("Looking for hourly CSV files on Cboe Europe")

            # One pass to collect all anchor hrefs across markets, then
            # filter per-market in Python — saves N DOM queries.
            all_anchors = await collect_anchor_urls(page, "a[href$='.csv']")
            total = 0
            for market in MARKETS:
                pattern = re.compile(
                    rf"rts13_public_trade_data_{market}_\d{{4}}-\d{{2}}-\d{{2}}_\d{{2}}\.csv$",
                    re.I,
                )
                market_csvs = [
                    (label, url) for (label, url) in all_anchors if pattern.search(url)
                ]
                self.logger.info("%s hourly files: %d", market.upper(), len(market_csvs))
                total += len(market_csvs)

                for _label, url in market_csvs:
                    filename = url.rsplit("/", 1)[-1]
                    await self._download_via_http(
                        page, url, f"cboe/{market}/hourly", filename,
                        post_delay=(0.2, 0.6),
                    )

            self.logger.info("Cboe done — total hourly files found: %d", total)
        finally:
            await page.close()
