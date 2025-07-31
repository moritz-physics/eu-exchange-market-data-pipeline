# german_scraper/exchanges/berlin.py
import re, pathlib
from .base import Exchange
from german_scraper.core.utils import click_first_consent, random_delay

PRE_URL  = "https://www.boerse-berlin.com/index.php/MiFid_2_Information/Pretrades"
POST_URL = "https://www.boerse-berlin.com/index.php/MiFid_2_Information/Post_Trade"

class Berlin(Exchange):
    name = "Börse Berlin"

    async def _process(self, page, url, regex, sub):
        await page.goto(url)
        await click_first_consent(page)
        links = await page.locator("a").filter(has_text=re.compile(regex, re.I)).all()
        print(f"🔍 {self.name}: {len(links)} links on {url}")
        for i, link in enumerate(links, 1):
            text = (await link.text_content()).strip()
            print(f"  [{i}/{len(links)}] {text}")
            if self.debug:
                await random_delay(1, 3)
                continue
            async with page.expect_download() as dl_info:
                await link.click()
            download = await dl_info.value
            await self.pipeline.save(download, sub)
            await random_delay(2, 8)

    async def run(self):
        page = await self.browser.new_page()
        await self._process(page, PRE_URL,  r"^Download der Pretrade Daten für ", "berlin/pretrade")
        await self._process(page, POST_URL, r"^Download der Daten für ", "berlin/posttrade")
        await page.close()
