# german_scraper/exchanges/lsx.py
import re, pathlib
from .base import Exchange
from german_scraper.core.utils import click_first_consent, random_delay

class LSX(Exchange):
    name = "Lang & Schwarz (ls-x.de)"

    async def run(self):
        page = await self.browser.new_page()
        await page.goto("https://www.ls-x.de/de/download")
        await click_first_consent(page)

        # ― Heute Download
        btn = page.get_by_role("row", name=re.compile("Heute Download", re.I)).get_by_role("button")
        if self.debug:
            print("(DEBUG) Would click Heute Download")
        else:
            async with page.expect_download() as dl:
                await btn.click()
            await self.pipeline.save(dl.value, "lsx")
            await random_delay(2, 5)

        # ― Pre-trade links
        links = await page.locator("a").filter(has_text=re.compile(r"^Pretrade Daten ", re.I)).all()
        print(f"🔍 LSX: {len(links)} pre-trade links")
        for i, link in enumerate(links, 1):
            text = (await link.text_content()).strip()
            print(f"  [{i}/{len(links)}] {text}")
            if self.debug:
                await random_delay(0.5, 1.5)
                continue
            async with page.expect_download() as dl:
                await link.click()
            await self.pipeline.save(dl.value, "lsx")
            await random_delay(2, 5)
        await page.close()
