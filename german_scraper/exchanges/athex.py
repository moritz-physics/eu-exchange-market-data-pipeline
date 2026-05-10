"""ATHEX (Greek Exchanges) delayed-feed scraper.

Three sections — APA Post-Trade, ATHEX Pre-Trade, ATHEX Post-Trade — each
behind a "View All" modal. CSV links inside the modal are deduplicated by
filename before download.
"""
from __future__ import annotations

import re
from typing import Optional

from playwright.async_api import Page

from .base import Exchange

SECTIONS: list[dict[str, str]] = [
    {
        "name": "AAPA-Post-Trade",
        "viewBtn": '#block-athex-tradeprepost-apapost-tableblock button:has-text("View All")',
    },
    {
        "name": "ATHEX-Pre-Trade",
        "viewBtn": '#block-athex-tradeprepost-athexpre-tableblock button:has-text("View All")',
    },
    {
        "name": "ATHEX-Post-Trade",
        "viewBtn": '#block-athex-tradeprepost-athexpost-tableblock button:has-text("View All")',
    },
]

HOME_URL: str = "https://www.athexgroup.gr/en/market-data/data-services/delayed-feed"


class ATHEX(Exchange):
    """ATHEX / Greek Exchanges delayed-feed downloads."""

    name: str = "ATHEX / Greek Exchanges"

    async def _reject_cookies(self, page: Page) -> None:
        try:
            reject = page.get_by_role("button", name=re.compile(r"Reject All", re.I))
            if await reject.is_visible():
                await reject.click()
                self.logger.info("Cookie banner rejected")
        except Exception:
            pass

    async def _download_section(self, page: Page, section: dict[str, str]) -> None:
        self.logger.info("Section: %s", section["name"])
        await page.locator(section["viewBtn"]).click()
        await page.wait_for_selector(
            '#athexGlobalModal a[href$=".csv"]', timeout=15_000
        )

        anchors = await page.locator('#athexGlobalModal a[href$=".csv"]').all()
        files: dict[str, object] = {}
        for a in anchors:
            href: Optional[str] = await a.get_attribute("href")
            if href:
                filename = href.split("/")[-1]
                files[filename] = a

        self.logger.info("%d unique file(s) detected", len(files))
        for filename, anchor in files.items():
            await self._download_via_click(
                page,
                anchor,  # type: ignore[arg-type]
                f"athex/{section['name']}",
                filename,
                post_delay=(0.1, 0.3),
            )

        await page.get_by_role("button", name="Close").click()
        await page.wait_for_selector(section["viewBtn"], state="visible")
        self.logger.info("Done with %s", section["name"])

    async def run(self) -> None:
        """Visit the delayed-feed page and download every CSV in every section."""
        page = await self.browser.new_page()
        try:
            await page.goto(HOME_URL)
            await self._reject_cookies(page)
            for section in SECTIONS:
                await self._download_section(page, section)
            self.logger.info("Finished all ATHEX sections")
        finally:
            await page.close()
