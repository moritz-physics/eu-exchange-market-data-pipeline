"""BME (Bolsas y Mercados Españoles) post-trade JSON scraper."""
from __future__ import annotations

import asyncio
import re
from typing import Optional

from playwright.async_api import Page

from .base import Exchange
from german_scraper.settings import SETTINGS

BME_URL: str = SETTINGS.exchange_url(
    "bme", "https://www.bolsasymercados.es/bme-exchange/en/post-trade-data"
)


class BME(Exchange):
    """BME (Spain) MiFID II post-trade JSON scraper."""

    name: str = "BME (Spain) Post-Trade"

    async def _accept_cookies_and_ok(self, page: Page) -> None:
        """Dismiss the OneTrust banner and the secondary modal."""
        try:
            accept_btn = page.locator("#onetrust-accept-btn-handler")
            await accept_btn.wait_for(state="visible", timeout=15_000)
            await accept_btn.click()
            self.logger.info("Clicked Accept All Cookies")
            await asyncio.sleep(3)
        except Exception as exc:
            self.logger.warning("Failed to click Accept All Cookies: %s", exc)

        try:
            ok_btn = page.locator("button.btn.btn-default[data-dismiss='modal']")
            await ok_btn.wait_for(state="visible", timeout=15_000)
            await ok_btn.click()
            self.logger.info("Clicked OK on second pop-up")
            await asyncio.sleep(3)
        except Exception as exc:
            self.logger.warning("Failed to click OK button: %s", exc)

    async def run(self) -> None:
        """Download every BMEA post-trade JSON anchor on the page."""
        page = await self.browser.new_page()
        try:
            await page.goto(BME_URL)
            await self._accept_cookies_and_ok(page)

            links = await page.locator("a").filter(
                has_text=re.compile(r"_BMEA_posttrade\.json$", re.I)
            ).all()
            self.logger.info("BME: %d post-trade JSON links", len(links))

            for link in links:
                text: Optional[str] = await link.text_content()
                filename = (text or "").strip()
                if not filename:
                    continue
                if self.debug:
                    self.logger.info("(DEBUG) Would download %s", filename)
                    continue
                if self.pipeline.has_seen(filename):
                    self.logger.info("(SKIP) Already downloaded: %s", filename)
                    continue
                try:
                    self.logger.info("Downloading %s", filename)
                    async with page.expect_download() as dl_info:
                        await link.click(modifiers=["Alt"])
                    download = await dl_info.value
                    await self.pipeline.save(download, "bme/post-trade")
                except Exception as exc:
                    self.logger.error("Failed to download %s: %s", filename, exc)
        finally:
            await page.close()
