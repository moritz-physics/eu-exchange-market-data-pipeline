# german_scraper/exchanges/lsx.py
import re
from .base import Exchange
from german_scraper.core.utils import click_first_consent
from german_scraper.core.throttle import random_delay

class LSX(Exchange):
    name = "Lang & Schwarz (ls-x.de)"

    async def run(self):
        page = await self.browser.new_page()
        await page.goto("https://www.ls-x.de/de/download")
        await click_first_consent(page)

        # ― Heute Download
        btn = page.get_by_role("row", name=re.compile("Heute Download", re.I)).get_by_role("button")
        heute_label = "Heute Download"
        if self.debug:
            print(f"(DEBUG) Would click {heute_label}")
            await random_delay(1, 2)
        else:
            if self.pipeline.has_seen(heute_label):
                print(f"(SKIP) Already downloaded: {heute_label}")
            else:
                async with page.expect_download() as dl:
                    await btn.click()
                await self.pipeline.save(dl.value, "lsx")
                await random_delay(2, 4)

        # ― Pre-trade links
        links = await page.locator("a").filter(has_text=re.compile(r"^Pretrade Daten ", re.I)).all()
        print(f"🔍 LSX: {len(links)} pre-trade links")
        for i, link in enumerate(links, 1):
            text = (await link.text_content()).strip()
            if self.debug:
                print(f"(DEBUG) [{i}/{len(links)}] Would download: {text}")
                await random_delay(0.5, 1.5)
                continue

            if self.pipeline.has_seen(text):
                print(f"(SKIP) [{i}/{len(links)}] Already downloaded: {text}")
                continue

            print(f"⬇️  [{i}/{len(links)}] Downloading: {text}")
            async with page.expect_download() as dl:
                await link.click()
            await self.pipeline.save(dl.value, "lsx")
            await random_delay(2, 4)
        await page.close()
