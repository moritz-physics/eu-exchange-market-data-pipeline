"""ICE delayed post-trade scraper.

Same login flow as :mod:`german_scraper.exchanges.ice`; targets the
post-trade report URL (``/report/61``).
"""
from __future__ import annotations

import asyncio
import os
import random
import re

from playwright.async_api import Page, TimeoutError

from .base import Exchange

PAGE_LOAD_WAIT: tuple[float, float] = (2.0, 4.0)
ICE_REPORT_URL: str = "https://www.ice.com/report/61"


class ICEPost(Exchange):
    """ICE Exchange post-trade scraper (paginated download buttons)."""

    name: str = "ICE Exchange (Post-Trade)"

    @staticmethod
    def _credentials() -> tuple[str, str]:
        email = os.environ.get("ICE_EMAIL")
        password = os.environ.get("ICE_PASSWORD")
        if not email or not password:
            raise RuntimeError(
                "ICE_EMAIL and ICE_PASSWORD environment variables must be set."
            )
        return email, password

    async def _human_wait(self, a: float, b: float) -> None:
        await asyncio.sleep(random.uniform(a, b))

    async def _accept_cookies(self, page: Page) -> None:
        await self._human_wait(1, 2)
        try:
            await page.get_by_role(
                "button", name=re.compile("Accept All Cookies", re.I)
            ).click()
            await self._human_wait(0.5, 1)
            await page.get_by_role("button", name=re.compile(r"I Accept", re.I)).click()
        except TimeoutError:
            self.logger.debug("ICE cookie banner not present")

    async def _login(self, page: Page) -> None:
        """Fill in credentials and prompt the user for a 2FA code."""
        email, password = self._credentials()
        await page.goto(ICE_REPORT_URL)
        await self._accept_cookies(page)
        await page.get_by_role(
            "link", name=re.compile("click here to login", re.I)
        ).click()
        await page.get_by_role("textbox", name=re.compile("Email", re.I)).fill(email)
        await page.get_by_role(
            "checkbox", name=re.compile("Remember User ID", re.I)
        ).check()
        await page.get_by_role("button", name=re.compile("^Next$", re.I)).click()
        await page.get_by_role("textbox", name=re.compile("Password", re.I)).fill(password)
        await page.get_by_role("button", name=re.compile("^Login$", re.I)).click()

        twofa = input("\nPlease enter your ICE 2FA code: ")
        await page.get_by_role(
            "textbox", name=re.compile("2FA Passcode", re.I)
        ).fill(twofa)
        await page.get_by_role("button", name=re.compile("^Login$", re.I)).click()
        self.logger.info("Logged in to ICE (Post-Trade)")

    async def _download_buttons_on_page(self, page: Page, page_idx: int) -> int:
        rows = page.locator("tr")
        buttons = rows.locator("button")
        n = await buttons.count()
        new_files = 0
        for i in range(n):
            btn = buttons.nth(i)
            row_text = await btn.locator("xpath=..").text_content() or f"row{i}"
            label = f"ICE POST page {page_idx}: {row_text.strip()}"
            saved = await self._download_via_click(
                page, btn, "ice_post", label, post_delay=(0.3, 0.7),
            )
            if saved:
                new_files += 1
        return new_files

    async def run(self) -> None:
        """Log in, then iterate every result page until 'Next' is disabled."""
        page = await self.browser.new_page()
        try:
            await self._login(page)
            page_idx = 1
            total_new = 0
            while True:
                await self._human_wait(*PAGE_LOAD_WAIT)
                total_new += await self._download_buttons_on_page(page, page_idx)
                try:
                    next_link = page.get_by_role("link", name=re.compile(r"Next", re.I))
                    if not await next_link.is_enabled():
                        self.logger.info("'Next' link disabled — last page")
                        break
                    await next_link.click()
                    page_idx += 1
                except TimeoutError:
                    self.logger.info("No 'Next' link found — last page")
                    break
            self.logger.info(
                "ICE post-trade finished — new files this run: %d", total_new,
            )
        finally:
            await page.close()
