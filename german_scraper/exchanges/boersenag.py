# german_scraper/exchanges/boersenag.py

import re
from playwright.async_api import TimeoutError
from .base import Exchange
from german_scraper.core.throttle import random_delay

class BoersenAG(Exchange):
    name = "Börsen AG (Düsseldorf/Hamburg/Hannover etc.)"

    async def _click_consent(self, page):
        try:
            await page.wait_for_selector("#CookieBoxSaveButton", timeout=10000)
            button = page.locator("#CookieBoxSaveButton")
            if await button.is_visible():
                await button.click()
                print("✅ Clicked consent button (Einwilligung speichern)")
            else:
                print("⚠️  Consent button appeared but not visible.")
        except TimeoutError:
            print("⚠️  Consent button did not appear (timeout)")

    async def _click_unlock(self, page):
        try:
            await page.wait_for_selector("a[role='button']", timeout=10000)
            unlock = page.locator("a[role='button']").filter(has_text="Inhalt entsperren").first
            if await unlock.is_visible():
                await unlock.click()
                print("✅ Clicked unlock button (Inhalt entsperren)")
            else:
                print("⚠️  Unlock <a> appeared but not visible.")
        except TimeoutError:
            print("⚠️  Unlock <a> with role='button' did not appear (timeout)")

    async def run(self):
        page = await self.browser.new_page()
        await page.goto("https://www.boersenag.de/mifid-ii-delayed-data/")

        # 1. Handle cookie banner
        await self._click_consent(page)

        # 2. Click "Inhalt entsperren"
        await self._click_unlock(page)

        # 3. Wait for iframe to be accessible
        try:
            iframe_locator = page.frame_locator("#mifid-iframe")
            await iframe_locator.locator("body").wait_for(timeout=10000)
        except TimeoutError:
            print("⚠️  iframe #mifid-iframe did not appear.")
            await page.close()
            return []

        # 4. Download links inside iframe
        link_selector = re.compile(r"Download der Daten für ", re.I)
        links = await iframe_locator.locator("a").filter(has_text=link_selector).all()
        print(f"🔍 boersenag: {len(links)} files")

        results = []

        for idx, link in enumerate(links, 1):
            label = (await link.text_content()).strip()

            if self.debug:
                print(f"(DEBUG) [{idx}/{len(links)}] Would download: {label}")
                await random_delay(0.5, 1.5)
                continue

            if self.pipeline.has_seen(label):
                print(f"(SKIP) [{idx}/{len(links)}] Already downloaded: {label}")
                continue

            print(f"⬇️  [{idx}/{len(links)}] Downloading: {label}")
            async with page.expect_download() as dl_info:
                await link.click()
            download = await dl_info.value
            path = await self.pipeline.save(download, "boersenag")
            results.append({"file": path, "source_link": label})
            await random_delay(1, 3)

        await page.close()
        return results
