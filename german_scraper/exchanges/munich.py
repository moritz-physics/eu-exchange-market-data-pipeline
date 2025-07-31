# german_scraper/exchanges/munich.py
import re
from .base import Exchange
from german_scraper.core.utils import click_first_consent, random_delay

class Munich(Exchange):
    name = "Börse München (gettex)"

    async def _download_links(self, page, pattern, sub):
        links = await page.locator("a").filter(has_text=re.compile(pattern, re.I)).all()
        print(f"🔍 {sub}: {len(links)} files")
        for i, link in enumerate(links, 1):
            text = (await link.text_content()).strip()
            print(f"  [{i}/{len(links)}] {text}")
            if self.debug:
                await random_delay(1, 2)
                continue
            async with page.expect_download() as dl_info:
                await link.click()
            await self.pipeline.save(dl_info.value, sub)
            await random_delay(2, 6)

    async def run(self):
        page = await self.browser.new_page()
        await page.goto("https://www.gettex.de/handel/delayed-data/")
        await click_first_consent(page)

        # Pre-trade tab
        await page.get_by_role("link", name=re.compile("MiFID II verzögerte pre-trade", re.I)).click()
        await self._download_links(page, r"^pretrade\..*\.csv\.gz$", "munich/pretrade")

        # Post-trade tab
        await page.goto("https://www.gettex.de/handel/delayed-data/")
        await page.get_by_role("link", name=re.compile("MiFID II verzögerte post-", re.I)).click()
        await self._download_links(page, r"^posttrade\..*\.csv\.(gz|jz)$", "munich/posttrade")

        await page.close()
