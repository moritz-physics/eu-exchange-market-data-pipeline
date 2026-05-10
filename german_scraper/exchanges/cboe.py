"""Cboe Europe equities trade-data scraper.

Downloads the per-market hourly RTS-13 public trade data CSVs across the
four Cboe markets: BXE, CXE, DXE, APA.
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional

from playwright.async_api import Page

from .base import Exchange

CBOE_URL: str = "https://www.cboe.com/europe/equities/trade_data/"
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

            total_found = 0
            for market in MARKETS:
                csv_links = await page.locator("a[href$='.csv']").all()
                pattern = re.compile(
                    rf"rts13_public_trade_data_{market}_\d{{4}}-\d{{2}}-\d{{2}}_\d{{2}}\.csv$",
                    re.I,
                )
                market_csvs: list[tuple[object, str]] = []
                for link in csv_links:
                    href: Optional[str] = await link.get_attribute("href")
                    if href and pattern.search(href):
                        market_csvs.append((link, href))

                self.logger.info("%s hourly files: %d", market.upper(), len(market_csvs))
                total_found += len(market_csvs)

                for link, href in market_csvs:
                    filename = href.split("/")[-1]
                    await self._download_via_click(
                        page, link, f"cboe/{market}/hourly", filename,  # type: ignore[arg-type]
                        post_delay=(0.5, 2.5),
                    )

            self.logger.info("Cboe done — total hourly files found: %d", total_found)
        finally:
            await page.close()
