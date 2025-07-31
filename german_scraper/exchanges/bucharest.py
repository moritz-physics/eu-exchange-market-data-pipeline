# german_scraper/exchanges/bucharest.py

import re
from .base import Exchange
from german_scraper.core.throttle import random_delay

MAIN_URL = 'https://www.bvb.ro/TradingAndStatistics/Trading/MiFIDIIData'

class Bucharest(Exchange):
    name = "Bucharest Stock Exchange (BVB)"

    async def _dismiss_popups(self, page):
        for label in ['Accept', 'OK', 'Close', 'Got it', 'Agree']:
            try:
                btn = page.get_by_role('button', name=re.compile(f"^{label}$", re.I))
                if await btn.is_visible():
                    print(f"⚡ Dismissing popup '{label}'")
                    await btn.click()
                    await page.wait_for_timeout(400)
            except Exception:
                continue

    async def run(self):
        page = await self.browser.new_page()

        # 1️⃣ Open main page and switch to English
        await page.goto(MAIN_URL)
        await self._dismiss_popups(page)

        enButton = page.get_by_text('EN', exact=True)
        if await enButton.is_visible():
            await enButton.click()
            print('🌐 Switched to English')
            await random_delay(1, 2)

        # 2️⃣ Pre-Trade: Quick download
        pre_link = page.get_by_role('link', name=re.compile(r'^Quick download$', re.I))
        pre_file = "Pre-Trade-Quick-Download"
        if self.debug:
            print('(DEBUG) Would download Pre-Trade file')
            await random_delay(1, 2)
        elif not await pre_link.is_visible():
            print('❌ Pre-Trade download link not found')
        elif self.pipeline.has_seen(pre_file):
            print(f'(SKIP) Pre-Trade file already downloaded: {pre_file}')
        else:
            async with page.expect_download() as dl_info:
                await pre_link.click()
            download = await dl_info.value
            await self.pipeline.save(download, "bucharest/Pre")
            await random_delay(1, 2)

        # 3️⃣ Navigate to Post-Trade page
        postPageLink = page.get_by_role('link', name=re.compile(r'Post - Trade', re.I))
        if not await postPageLink.is_visible():
            print('❌ Post-Trade page link not found')
            await page.close()
            return
        await postPageLink.click()
        print('🔀 Moved to Post-Trade section')
        await self._dismiss_popups(page)

        # 4️⃣ Post-Trade: Current file
        current_link = page.get_by_role('link', name=re.compile(r'Quick download - Current', re.I))
        current_file = "Post-Trade-Quick-Download-Current"
        if self.debug:
            print('(DEBUG) Would download Post-Trade Current file')
            await random_delay(1, 2)
        elif not await current_link.is_visible():
            print('❌ Post-Trade Current link not found')
        elif self.pipeline.has_seen(current_file):
            print(f'(SKIP) Post-Trade Current file already downloaded: {current_file}')
        else:
            async with page.expect_download() as dl_info:
                await current_link.click()
            download = await dl_info.value
            await self.pipeline.save(download, "bucharest/Post")
            await random_delay(1, 2)

        # 5️⃣ Post-Trade: Previous file
        prev_link = page.get_by_role('link', name=re.compile(r'Quick download - Previous', re.I))
        prev_file = "Post-Trade-Quick-Download-Previous"
        if self.debug:
            print('(DEBUG) Would download Post-Trade Previous file')
            await random_delay(1, 2)
        elif not await prev_link.is_visible():
            print('❌ Post-Trade Previous link not found')
        elif self.pipeline.has_seen(prev_file):
            print(f'(SKIP) Post-Trade Previous file already downloaded: {prev_file}')
        else:
            async with page.expect_download() as dl_info:
                await prev_link.click()
            download = await dl_info.value
            await self.pipeline.save(download, "bucharest/Post")
            await random_delay(1, 2)

        print('✅ All Bucharest files handled.')
        await page.close()
