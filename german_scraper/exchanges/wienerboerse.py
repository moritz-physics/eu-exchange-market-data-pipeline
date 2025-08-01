# german_scraper/exchanges/wienerboerse.py
#works sometimes but also fails sometimes i dont yet know why

import random
import asyncio
from .base import Exchange
from german_scraper.core.throttle import random_delay

URLS = [
    ("Prices Tab 2", "https://prices.wienerborse.at/#tab-content2"),
    ("Prices Tab 3", "https://prices.wienerborse.at/#tab-content3"),
    ("Prices Tab 4", "https://prices.wienerborse.at/#tab-content4"),
]

class WienerBoerse(Exchange):
    name = "Wiener Börse"

    async def run(self):
        page = await self.browser.new_page()

        for tab_name, url in URLS:
            print(f"\n🔗 Navigating to: {url} ({tab_name})")
            await page.goto(url)
            wait_time = random.uniform(5, 8)
            print(f"⏳ Waiting {wait_time:.1f} seconds for page to load...")
            await asyncio.sleep(wait_time)

            # Special reload for Tab 2 (first in the list)
            if tab_name == "Prices Tab 2":
                print("🔄 Reloading Tab 2 page once to ensure full load...")
                await page.reload()
                wait_time = random.uniform(5, 7)
                print(f"⏳ Waiting {wait_time:.1f} seconds after reload...")
                await asyncio.sleep(wait_time)

            btn = page.locator("button.downloadbtn.btn.btn-primary")
            try:
                await btn.wait_for(state="visible", timeout=15000)
            except Exception:
                print(f"⚠️  Download button not found on {tab_name}, skipping.")
                continue

            btn_text = await btn.text_content()
            btn_label = f"{tab_name}: {btn_text.strip() if btn_text else 'Download'}"
            print(f"🟢 Found button: {btn_label}")

            if self.debug:
                print(f"(DEBUG) Would click {btn_label}")
                await random_delay(1, 2)
                continue

            if self.pipeline.has_seen(btn_label):
                print(f"(SKIP) Already downloaded: {btn_label}")
                continue

            print(f"⬇️  Clicking to download: {btn_label}")
            async with page.expect_download() as dl_info:
                await btn.click()
            download = await dl_info.value
            await self.pipeline.save(download, "wienerboerse")
            await random_delay(2, 4)

        await page.close()
