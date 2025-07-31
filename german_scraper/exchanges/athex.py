# german_scraper/exchanges/athex.py

import re
from .base import Exchange
from german_scraper.core.throttle import random_delay

SECTIONS = [
    {
        "name": "AAPA-Post-Trade",
        "viewBtn": '#block-athex-tradeprepost-apapost-tableblock button:has-text("View All")',
    },
    {
        "name": "ATHEX-Pre-Trade",
        "viewBtn": '#block-athex-tradeprepost-athexpre-tableblock button:has-text("View All")',
    },
    {
        "name": "ATHEX-Post-Trade",
        "viewBtn": '#block-athex-tradeprepost-athexpost-tableblock button:has-text("View All")',
    },
]

HOME_URL = "https://www.athexgroup.gr/en/market-data/data-services/delayed-feed"

class ATHEX(Exchange):
    name = "ATHEX / Greek Exchanges"

    async def _reject_cookies(self, page):
        reject = page.get_by_role("button", name=re.compile(r"Reject All", re.I))
        if await reject.is_visible():
            await reject.click()
            print("🍪 cookie banner rejected")

    async def _download_section(self, page, section):
        print(f"\n📂 SECTION ▶ {section['name']}")
        await page.locator(section["viewBtn"]).click()
        await page.wait_for_selector('#athexGlobalModal a[href$=".csv"]', timeout=15000)

        # Collect and deduplicate all CSV links by filename
        anchors = await page.locator('#athexGlobalModal a[href$=".csv"]').all()
        files = dict()
        for a in anchors:
            href = await a.get_attribute('href')
            if href:
                filename = href.split('/')[-1]
                files[filename] = a

        print(f"🔗  {len(files)} file(s) detected")
        idx = 0
        for file, anchor in files.items():
            idx += 1
            print(f"➡️  {idx}/{len(files)}  {file}")
            if self.debug:
                print("   ↪ (debug) would download")
                await random_delay(0.1, 0.3)
                continue
            if self.pipeline.has_seen(file):
                print("   ↪ already exists, skipping")
                continue
            async with page.expect_download() as dl_info:
                await anchor.click()
            download = await dl_info.value
            await self.pipeline.save(download, f"athex/{section['name']}")
            await random_delay(0.1, 0.3)

        # Close modal and wait for section view button to be visible again
        await page.get_by_role("button", name="Close").click()
        await page.wait_for_selector(section["viewBtn"], state="visible")
        print(f"✅ done with {section['name']}")

    async def run(self):
        page = await self.browser.new_page()
        await page.goto(HOME_URL)
        await self._reject_cookies(page)

        for section in SECTIONS:
            await self._download_section(page, section)

        print('\n🏁 finished all sections')
        await page.close()
