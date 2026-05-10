"""Börse München (gettex) delayed-data scraper.

Pre- and post-trade links sometimes open a popup tab and sometimes navigate
the current tab. ``_open_data_window`` transparently returns the right
``Page`` either way.
"""
from __future__ import annotations

import re
from typing import Optional

from playwright.async_api import Page, TimeoutError

from .base import Exchange
from german_scraper.core.utils import click_first_consent


class Munich(Exchange):
    """Boerse München (gettex) pre & post-trade downloads."""

    name: str = "Börse München (gettex)"

    async def _open_data_window(self, page: Page, link_locator) -> Page:
        """Click ``link_locator`` and return the page that holds the file table."""
        try:
            popup_future = page.wait_for_event("popup", timeout=5_000)
            await link_locator.click()
            popup = await popup_future
            return popup
        except TimeoutError:
            await link_locator.click()
            return page

    async def _download_every_link(self, data_page: Page, pattern: str, subdir: str) -> None:
        """Download every anchor on ``data_page`` whose text matches ``pattern``."""
        links = await data_page.locator("a").filter(
            has_text=re.compile(pattern, re.I)
        ).all()
        self.logger.info("%s: %d files", subdir, len(links))

        for link in links:
            text: Optional[str] = await link.text_content()
            label = (text or "").strip()
            if not label:
                continue
            await self._download_via_click(
                data_page, link, subdir, label, post_delay=(2.0, 4.0),
            )

    async def run(self) -> None:
        """Scrape pre-trade then post-trade tables."""
        page = await self.browser.new_page()
        try:
            await page.goto("https://www.gettex.de/handel/delayed-data/")
            await click_first_consent(page)

            pretrade_link = page.get_by_role(
                "link", name=re.compile(r"MiFID II verzögerte pre-trade", re.I)
            )
            pre_page = await self._open_data_window(page, pretrade_link)
            await self._download_every_link(
                pre_page, pattern=r"^pretrade\.", subdir="munich/pretrade",
            )
            if pre_page is not page:
                await pre_page.close()

            if page.url != "https://www.gettex.de/handel/delayed-data/":
                await page.goto("https://www.gettex.de/handel/delayed-data/")
            posttrade_link = page.get_by_role(
                "link", name=re.compile(r"MiFID II verzögerte post-", re.I)
            )
            post_page = await self._open_data_window(page, posttrade_link)
            await self._download_every_link(
                post_page, pattern=r"^posttrade\.", subdir="munich/posttrade",
            )
            if post_page is not page:
                await post_page.close()
        finally:
            await page.close()
