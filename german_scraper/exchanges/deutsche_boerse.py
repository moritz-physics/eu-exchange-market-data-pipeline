"""Deutsche Börse MiFID II disaggregated delayed-data scraper.

Replaces the legacy Selenium + Firefox scraper (archived under
``legacy/deutsche-boerse-selenium/``) with a Playwright
:class:`~german_scraper.exchanges.base.Exchange` subclass, so it gains
the manifest dedupe, retry/backoff, metrics and DQ gates of the rest of
the pipeline.

Flow
====

The MDS portal lists each venue's pre/post-trade file service as a
table row. Clicking the row opens a popup page that lists the actual
``.json.gz`` download anchors. The set of rows to visit is configurable
via ``config.json`` → ``deutsche_boerse.rows`` (e.g.
``"Xetra – Pre-Trade File service"``), so adding Frankfurt / Eurex /
Tradegate pre- and post-trade rows needs no code change.
"""
from __future__ import annotations

import re

from playwright.async_api import Page, TimeoutError

from .base import Exchange
from german_scraper.settings import SETTINGS

BASE_URL: str = SETTINGS.exchange_url(
    "deutsche_boerse",
    "https://www.mds.deutsche-boerse.com/mds-en/real-time-data/"
    "MiFID-II-Disaggregated-Information-Products-delayed--1520116",
)


class DeutscheBoerse(Exchange):
    """Deutsche Börse (Xetra / Frankfurt / Eurex / Tradegate) delayed data."""

    name: str = "Deutsche Börse (MDS delayed data)"
    download_subdir: str = "deutsche-boerse"
    max_files_per_row: int = 100

    async def _accept_cookies(self, page: Page) -> None:
        """Dismiss the cookie / AGB banner if present (best-effort)."""
        try:
            btn = page.get_by_role(
                "button", name=re.compile(r"I agree|Accept all|^OK$", re.I)
            )
            await btn.click(timeout=5_000)
            self.logger.info("Cookie banner accepted")
        except TimeoutError:
            self.logger.debug("No cookie banner present")

    async def _scrape_row(self, page: Page, row_label: str) -> None:
        """Open the popup for one row and download its ``.json.gz`` anchors."""
        self.logger.info("Row: %s", row_label)
        row_link = page.get_by_role("row", name=row_label).get_by_role("link")
        try:
            async with page.expect_popup(timeout=15_000) as popup_info:
                await row_link.click()
            popup = await popup_info.value
        except TimeoutError:
            self.logger.error("Row %r did not open a popup page", row_label)
            return

        try:
            await self._accept_cookies(popup)
            await popup.wait_for_load_state("domcontentloaded")
            # The popup renders its (often 1000+) .json.gz anchors after
            # load — wait for the first one rather than counting too early.
            try:
                await popup.wait_for_selector(
                    'a[href$=".json.gz"]', timeout=20_000
                )
            except TimeoutError:
                self.logger.warning(
                    "%s: no .json.gz files appeared on the popup", row_label
                )
                return
            anchors = popup.locator('a[href$=".json.gz"]')
            count = await anchors.count()
            self.logger.info("%s: %d .json.gz files", row_label, count)
            for i in range(min(count, self.max_files_per_row)):
                anchor = anchors.nth(i)
                label = (await anchor.get_attribute("href")) or f"{row_label}#{i}"
                await self._download_via_click(
                    popup, anchor, self.download_subdir, label,
                    post_delay=(2.0, 4.0),
                )
        finally:
            await popup.close()

    async def run(self) -> None:
        """Visit each configured row and download its delayed-data files."""
        page = await self.browser.new_page()
        try:
            await page.goto(BASE_URL)
            await self._accept_cookies(page)
            for row_label in SETTINGS.deutsche_boerse_rows():
                try:
                    await self._scrape_row(page, row_label)
                except Exception as exc:  # one bad row must not abort the rest
                    self.logger.error("Row %r failed: %s", row_label, exc)
        finally:
            await page.close()
