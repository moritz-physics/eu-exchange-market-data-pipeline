"""Bank of Greece HDAT pre & post-trade JSON scraper.

The HDAT data is exposed as plain JSON anchors. Playwright is used only
to navigate the two-step page flow (the post-trade page is reached via
the "Electronic Secondary" → "Post-trade data" submenu); the JSON files
themselves stream over HTTP.
"""
from __future__ import annotations

from .base import Exchange

PRE_URL: str = (
    "https://www.bankofgreece.gr/en/main-tasks/markets/hdat/pre-trade-data"
    "#:~:text=HDAT%20makes%20pre,600%2F2014%20%28MIFIR"
)


class BankOfGreece(Exchange):
    """Bank of Greece HDAT (Hellenic Debt securities Automated Trading) feed."""

    name: str = "Bank of Greece"

    async def _resolve_and_download(
        self, page, link, subdir: str, fallback_name: str,
    ) -> None:
        """Read href off ``link`` and stream via the HTTP fast path."""
        href = await link.get_attribute("href")
        if not href:
            self.logger.error("No href on %s", fallback_name)
            return
        # Absolutise relative URLs against the current page.
        if href.startswith("/"):
            href = f"https://www.bankofgreece.gr{href}"
        await self._download_via_http(
            page, href, subdir, fallback_name, post_delay=(1.0, 2.0),
        )

    async def run(self) -> None:
        """Download both PreTradeHDAT.json and PostTradeHDAT.json."""
        page = await self.browser.new_page()
        try:
            await page.goto(PRE_URL)

            pre_link = page.get_by_role("link", name="PreTradeHDAT.json i")
            await self._resolve_and_download(
                page, pre_link, "bank-of-greece/Pre-Trade", "PreTradeHDAT.json",
            )

            await page.get_by_role("link", name="Electronic Secondary").click()
            await page.get_by_role("link", name="Post-trade data").click()

            post_link = page.get_by_role("link", name="PostTradeHDAT.json i")
            await self._resolve_and_download(
                page, post_link, "bank-of-greece/Post-Trade", "PostTradeHDAT.json",
            )
            self.logger.info("Bank of Greece done")
        finally:
            await page.close()
