"""Borsa Bulgaria (BSE Sofia) APA trading-data scraper.

Ported from the first-generation ``borsa_bulgaria_test.spec.js``
prototype (now archived under ``legacy/``). The APA trading-data page
exposes a single CSV export behind a "Got it!" cookie banner — one
click on the "CSV with separator [ ; ]" link triggers the download.
"""
from __future__ import annotations

from playwright.async_api import Page

from .base import Exchange
from german_scraper.settings import SETTINGS

BSE_URL: str = SETTINGS.exchange_url(
    "bulgaria", "https://www.bse-sofia.bg/en/apa-trading-data"
)


class BorsaBulgaria(Exchange):
    """Borsa Bulgaria (bse-sofia.bg) APA trading-data CSV scraper."""

    name: str = "Borsa Bulgaria (BSE Sofia)"

    async def _dismiss_consent(self, page: Page) -> None:
        """Click the "Got it!" cookie banner if present (best-effort)."""
        try:
            btn = page.get_by_text("Got it!", exact=False)
            if await btn.is_visible():
                await btn.click()
                self.logger.info("Dismissed cookie banner")
        except Exception as exc:  # consent is best-effort, never fatal
            self.logger.debug("No cookie banner clicked (%s)", exc)

    async def run(self) -> None:
        """Open the APA page, dismiss consent, download the CSV export."""
        page = await self.browser.new_page()
        try:
            await page.goto(BSE_URL)
            await self._dismiss_consent(page)

            # The CSV export is an <img title="CSV with separator [ ; ]">
            # inside a javascript:void(0) anchor. Match a stable substring
            # of the title attribute; clicking the image fires the anchor's
            # download handler.
            export = page.locator(
                'img[title*="CSV with separator"]'
            ).first
            try:
                await export.wait_for(state="visible", timeout=15_000)
            except Exception:
                self.logger.error("Borsa Bulgaria CSV export control not found")
                return
            await self._download_via_click(
                page, export, "bulgaria", "APA trading data CSV",
                post_delay=(1.0, 2.0),
            )
        finally:
            await page.close()
