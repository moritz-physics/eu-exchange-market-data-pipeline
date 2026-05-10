"""Bank of Greece HDAT pre & post-trade JSON scraper."""
from __future__ import annotations

from .base import Exchange

PRE_URL: str = (
    "https://www.bankofgreece.gr/en/main-tasks/markets/hdat/pre-trade-data"
    "#:~:text=HDAT%20makes%20pre,600%2F2014%20%28MIFIR"
)


class BankOfGreece(Exchange):
    """Bank of Greece HDAT (Hellenic Debt securities Automated Trading) feed."""

    name: str = "Bank of Greece"

    async def run(self) -> None:
        """Download both PreTradeHDAT.json and PostTradeHDAT.json."""
        page = await self.browser.new_page()
        try:
            await page.goto(PRE_URL)

            pre_link = page.get_by_role("link", name="PreTradeHDAT.json i")
            await self._download_via_click(
                page, pre_link, "bank-of-greece/Pre-Trade",
                "PreTradeHDAT.json", post_delay=(1.0, 2.0),
            )

            await page.get_by_role("link", name="Electronic Secondary").click()
            await page.get_by_role("link", name="Post-trade data").click()

            post_link = page.get_by_role("link", name="PostTradeHDAT.json i")
            await self._download_via_click(
                page, post_link, "bank-of-greece/Post-Trade",
                "PostTradeHDAT.json", post_delay=(1.0, 2.0),
            )
            self.logger.info("Bank of Greece done")
        finally:
            await page.close()
