"""Lang & Schwarz Exchange (ls-x.de) pre-trade scraper.

Two flows are handled:
  1. The "Heute Download" button (intra-day pre-trade snapshot).
  2. The list of dated "Pretrade Daten" anchors.
"""
from __future__ import annotations

import re
from typing import Optional

from playwright.async_api import Page

from .base import Exchange


async def _click_akzeptieren(page: Page) -> None:
    """Wait for and click the 'Akzeptieren' consent button if present."""
    try:
        btn = page.locator("button.btn.btn-primary.accept")
        await btn.wait_for(state="visible", timeout=10_000)
        await btn.click()
        await page.wait_for_timeout(400)
    except Exception:
        pass


class LSX(Exchange):
    """Lang & Schwarz pre-trade scraper."""

    name: str = "Lang & Schwarz (ls-x.de)"

    async def run(self) -> None:
        """Download today's snapshot plus all dated pre-trade files."""
        page = await self.browser.new_page()
        try:
            await page.goto("https://www.ls-x.de/de/download")
            await _click_akzeptieren(page)

            heute_btn = page.get_by_role("row", name=re.compile("Heute Download", re.I)).get_by_role("button")
            await self._download_via_click(
                page, heute_btn, "lsx", "Heute Download", post_delay=(2.0, 4.0),
            )

            links = await page.locator("a").filter(
                has_text=re.compile(r"^Pretrade Daten ", re.I)
            ).all()
            self.logger.info("LSX: %d pre-trade links", len(links))
            for link in links:
                text: Optional[str] = await link.text_content()
                label = (text or "").strip()
                if not label:
                    continue
                await self._download_via_click(
                    page, link, "lsx", label, post_delay=(2.0, 4.0),
                )
        finally:
            await page.close()
