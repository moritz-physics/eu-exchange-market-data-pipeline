# german_scraper/exchanges/bme.py
#download all post-trade data from BME (Bolsas y Mercados Españoles) from today and yesterday

import re
import asyncio
from .base import Exchange
from german_scraper.core.throttle import random_delay

BME_URL = "https://www.bolsasymercados.es/bme-exchange/en/post-trade-data"

class BME(Exchange):
    name = "BME (Spain) Post-Trade"

    async def accept_cookies_and_ok(self, page):
        # Accept All Cookies (by id)
        try:
            accept_btn = page.locator("#onetrust-accept-btn-handler")
            await accept_btn.wait_for(state="visible", timeout=15000)
            await accept_btn.click()
            print("🍪 Clicked Accept All Cookies (by id)")
            await asyncio.sleep(3)
        except Exception as e:
            print(f"⚠️  Failed to click Accept All Cookies: {e}")

        # Second pop-up: Ok (by class and data-dismiss attr)
        try:
            ok_btn = page.locator("button.btn.btn-default[data-dismiss='modal']")
            await ok_btn.wait_for(state="visible", timeout=15000)
            await ok_btn.click()
            print("✅ Clicked Ok on second pop-up (by class)")
            await asyncio.sleep(3)
        except Exception as e:
            print(f"⚠️  Failed to click Ok button: {e}")

    async def run(self):
        page = await self.browser.new_page()
        await page.goto(BME_URL)
        await self.accept_cookies_and_ok(page)

        # Find all links ending in _BMEA_posttrade.json (like codegen)
        links = await page.locator("a").filter(has_text=re.compile(r"_BMEA_posttrade\.json$", re.I)).all()
        print(f"🗂 Found {len(links)} post-trade JSON links")

        for idx, link in enumerate(links, 1):
            label = (await link.text_content()).strip()
            filename = label  # Use the link text as the file name

            print(f"  [{idx}/{len(links)}] {filename}")

            if self.debug:
                print(f"   (DEBUG) Would download {filename}")
                await random_delay(0.5, 1.5)
                continue

            if self.pipeline.has_seen(filename):
                print(f"   (SKIP) Already downloaded: {filename}")
                continue

            # Option/Alt-click for download
            async with page.expect_download() as dl_info:
                await link.click(modifiers=["Alt"])
            download = await dl_info.value
            await self.pipeline.save(download, "bme/post-trade")
            await random_delay(0.8, 2.0)

        await page.close()
