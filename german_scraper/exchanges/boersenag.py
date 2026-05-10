"""Börsen AG (Düsseldorf, Hamburg, Hannover) MiFID II delayed-data scraper.

The download links live inside an iframe behind a "Inhalt entsperren" gate.
This scraper handles the cookie banner, unlocks the iframe, then iterates
every download anchor inside it.
"""
from __future__ import annotations

import re
from typing import Optional

from playwright.async_api import Page, TimeoutError

from .base import Exchange


class BoersenAG(Exchange):
    """Boersen AG umbrella of regional German exchanges."""

    name: str = "Börsen AG (Düsseldorf/Hamburg/Hannover etc.)"

    async def _click_consent(self, page: Page) -> None:
        try:
            await page.wait_for_selector("#CookieBoxSaveButton", timeout=10_000)
            button = page.locator("#CookieBoxSaveButton")
            if await button.is_visible():
                await button.click()
                self.logger.info("Clicked consent button")
        except TimeoutError:
            self.logger.warning("Consent button did not appear")

    async def _click_unlock(self, page: Page) -> None:
        try:
            await page.wait_for_selector("a[role='button']", timeout=10_000)
            unlock = page.locator("a[role='button']").filter(
                has_text="Inhalt entsperren"
            ).first
            if await unlock.is_visible():
                await unlock.click()
                self.logger.info("Clicked unlock button")
        except TimeoutError:
            self.logger.warning("Unlock anchor did not appear")

    async def run(self) -> None:
        """Open the page, dismiss cookie + unlock, then iterate iframe links."""
        page = await self.browser.new_page()
        try:
            await page.goto("https://www.boersenag.de/mifid-ii-delayed-data/")
            await self._click_consent(page)
            await self._click_unlock(page)

            try:
                iframe_locator = page.frame_locator("#mifid-iframe")
                await iframe_locator.locator("body").wait_for(timeout=10_000)
            except TimeoutError:
                self.logger.error("iframe #mifid-iframe did not appear")
                return

            link_pattern = re.compile(r"Download der Daten für ", re.I)
            links = await iframe_locator.locator("a").filter(has_text=link_pattern).all()
            self.logger.info("BoersenAG: %d files", len(links))

            for link in links:
                text: Optional[str] = await link.text_content()
                label = (text or "").strip()
                if not label:
                    continue
                await self._download_via_click(
                    page, link, "boersenag", label, post_delay=(1.0, 3.0),
                )
        finally:
            await page.close()
