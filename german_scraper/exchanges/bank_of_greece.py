# german_scraper/exchanges/bank_of_greece.py

import re
from .base import Exchange
from german_scraper.core.throttle import random_delay

PRE_URL = 'https://www.bankofgreece.gr/en/main-tasks/markets/hdat/pre-trade-data#:~:text=HDAT%20makes%20pre,600%2F2014%20%28MIFIR'

class BankOfGreece(Exchange):
    name = "Bank of Greece"

    async def run(self):
        page = await self.browser.new_page()

        # 1️⃣ Go to pre-trade page
        await page.goto(PRE_URL)

        # 2️⃣ Download PreTradeHDAT.json i
        pre_link = page.get_by_role('link', name="PreTradeHDAT.json i")
        pre_file = "PreTradeHDAT.json"
        if self.debug:
            print(f"(DEBUG) Would click PreTrade link")
            await random_delay(1, 2)
        elif self.pipeline.has_seen(pre_file):
            print(f"(SKIP) Already downloaded: {pre_file}")
        else:
            async with page.expect_download() as dl_info:
                await pre_link.click()
            download = await dl_info.value
            await self.pipeline.save(download, "bank-of-greece/Pre-Trade")
            await random_delay(1, 2)

        # 3️⃣ Navigate to post-trade page
        await page.get_by_role('link', name="Electronic Secondary").click()
        await page.get_by_role('link', name="Post-trade data").click()

        # 4️⃣ Download PostTradeHDAT.json i
        post_link = page.get_by_role('link', name="PostTradeHDAT.json i")
        post_file = "PostTradeHDAT.json"
        if self.debug:
            print(f"(DEBUG) Would click PostTrade link")
            await random_delay(1, 2)
        elif self.pipeline.has_seen(post_file):
            print(f"(SKIP) Already downloaded: {post_file}")
        else:
            async with page.expect_download() as dl_info:
                await post_link.click()
            download = await dl_info.value
            await self.pipeline.save(download, "bank-of-greece/Post-Trade")
            await random_delay(1, 2)

        print("✅ done")
        await page.close()
