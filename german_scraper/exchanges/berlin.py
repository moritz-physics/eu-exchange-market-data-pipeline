# german_scraper/exchanges/berlin.py
#maybe check if posttrades works 

import re
from .base import Exchange
from german_scraper.core.utils import click_first_consent
from german_scraper.core.throttle import random_delay

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
            if self.debug:
                print(f"(DEBUG) [{i}/{len(links)}] Would download: {text}")
                await random_delay(1, 3)
                continue

            if self.pipeline.has_seen(text):
                print(f"(SKIP) [{i}/{len(links)}] Already downloaded: {text}")
                continue

            print(f"⬇️  [{i}/{len(links)}] Downloading: {text}")
            async with page.expect_download() as dl_info:
                await link.click()
            download = await dl_info.value
            await self.pipeline.save(download, sub)
            await random_delay(2, 6)

    async def run(self):
        page = await self.browser.new_page()
        await self._process(page, PRE_URL,  r"^Download der Pretrade Daten für ", "berlin/pretrade")
        await self._process(page, POST_URL, r"^Download der Daten für ", "berlin/posttrade")
        await page.close()
