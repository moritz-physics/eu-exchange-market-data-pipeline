# german_scraper/exchanges/ice_post.py
"""
ICE Post-Trade delayed data scraper.
- Handles login and downloads every file on every result page.
- Prompts user for 2FA code at runtime.
- Dedupes via manifest/pipeline, fits modular workflow.
"""

import asyncio, random, re
from playwright.async_api import TimeoutError
from .base import Exchange
from german_scraper.core.throttle import random_delay

ICE_EMAIL    = "heidtmann.moritz@gmail.com"     # your ICE email
ICE_PASSWORD = "Finance2024"
# 2FA code will be prompted from user on each run

PAGE_LOAD_WAIT = (2, 4)   # seconds between result pages

class ICEPost(Exchange):
    name = "ICE Exchange (Post-Trade)"

    async def _human_wait(self, a: float, b: float):
        """Sleep between a…b seconds (float)."""
        await asyncio.sleep(random.uniform(a, b))

    async def _accept_cookies(self, page):
        await self._human_wait(1, 2)
        try:
            await page.get_by_role("button", name=re.compile("Accept All Cookies", re.I)).click()
            await self._human_wait(0.5, 1)
            await page.get_by_role("button", name=re.compile(r"I Accept", re.I)).click()
        except TimeoutError:
            print("⚠️  Cookie banner not present or already dismissed.")

    async def _login(self, page):
        """Automates ICE login; prompts user for 2FA code."""
        await page.goto("https://www.ice.com/report/61")
        await self._accept_cookies(page)
        await page.get_by_role("link", name=re.compile("click here to login", re.I)).click()
        await page.get_by_role("textbox", name=re.compile("Email", re.I)).fill(ICE_EMAIL)
        await page.get_by_role("checkbox", name=re.compile("Remember User ID", re.I)).check()
        await page.get_by_role("button", name=re.compile("^Next$", re.I)).click()
        await page.get_by_role("textbox", name=re.compile("Password", re.I)).fill(ICE_PASSWORD)
        await page.get_by_role("button", name=re.compile("^Login$", re.I)).click()

        # PROMPT USER for 2FA code from SMS/app/email
        twofa = input("\n🔐 Please enter your ICE 2FA code: ")
        await page.get_by_role("textbox", name=re.compile("2FA Passcode", re.I)).fill(twofa)
        await page.get_by_role("button", name=re.compile("^Login$", re.I)).click()

        print("✅ Logged in to ICE (Post-Trade)")

    async def _download_buttons_on_page(self, page, page_idx: int):
        """
        Click every button in the results table that triggers a file download.
        Returns number of new files downloaded on this page.
        """
        rows = page.locator("tr")          # table rows
        buttons = rows.locator("button")   # download buttons inside rows
        n = await buttons.count()
        new_files = 0

        for i in range(n):
            btn = buttons.nth(i)
            row_text = (await btn.locator("xpath=..").text_content()) or f"row{i}"
            label = f"ICE POST page {page_idx}: {row_text.strip()}"

            if self.debug:
                print(f"(DEBUG) Would download: {label}")
                continue
            if self.pipeline.has_seen(label):
                print(f"(SKIP) Already downloaded: {label}")
                continue

            try:
                async with page.expect_download() as dl_info:
                    await btn.click()
                download = await dl_info.value
                await self.pipeline.save(download, "ice_post")
                new_files += 1
                await random_delay(0.3, 0.7)   # quick delay, many files per page
            except Exception as e:
                print(f"❌ Failed to download {label}: {e}")

        return new_files

    async def run(self):
        page = await self.browser.new_page()
        await self._login(page)

        page_idx = 1
        total_new = 0

        while True:
            await self._human_wait(*PAGE_LOAD_WAIT)
            new_this_page = await self._download_buttons_on_page(page, page_idx)
            total_new += new_this_page

            # Try to click “Next ›” link; if disabled/absent, break
            try:
                next_link = page.get_by_role("link", name=re.compile(r"Next", re.I))
                if not await next_link.is_enabled():
                    print("➡️  ‘Next’ link disabled – reached last page.")
                    break
                await next_link.click()
                page_idx += 1
            except TimeoutError:
                print("➡️  No ‘Next’ link found – reached last page.")
                break

        print(f"✅ ICE POST finished – new files this run: {total_new}")
        await page.close()
