# german_scraper/exchanges/munich.py
"""
Scraper for Börse München (gettex) delayed-data downloads.
Works whether the exchange opens a popup or keeps everything in the same tab.
Integrates random delay and skip-if-already-downloaded logic.
"""

import re
from playwright.async_api import TimeoutError
from .base import Exchange
from german_scraper.core.utils import click_first_consent
from german_scraper.core.throttle import random_delay


class Munich(Exchange):
    name = "Börse München (gettex)"

    # -------------------- internal helpers --------------------

    async def _open_data_window(self, page, link_locator):
        """
        Clicks a link (pre-trade or post-trade) and returns the Page object
        that contains the table of downloadable files.
        """
        try:
            popup_future = page.wait_for_event("popup", timeout=5_000)
            await link_locator.click()
            popup = await popup_future
            return popup
        except TimeoutError:
            await link_locator.click()
            return page

    async def _download_every_link(self, data_page, pattern, subdir):
        """
        Finds every <a> whose text matches `pattern`,
        skips if already downloaded, otherwise saves it.
        """
        links = await data_page.locator("a").filter(
            has_text=re.compile(pattern, re.I)
        ).all()

        print(f"🔍 {subdir}: {len(links)} files")

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
            async with link.page.expect_download() as dl_info:
                await link.click()
            download = await dl_info.value
            await self.pipeline.save(download, subdir)
            await random_delay(2, 4)

    # -------------------- public entry point --------------------

    async def run(self):
        """Main workflow for the Munich scraper."""
        page = await self.browser.new_page()
        await page.goto("https://www.gettex.de/handel/delayed-data/")
        await click_first_consent(page)

        # -------- Pre-trade --------
        pretrade_link = page.get_by_role(
            "link", name=re.compile(r"MiFID II verzögerte pre-trade", re.I)
        )
        pre_page = await self._open_data_window(page, pretrade_link)
        await self._download_every_link(
            pre_page,
            pattern=r"^pretrade\.",          # match any pretrade.* file
            subdir="munich/pretrade",
        )
        if pre_page is not page:
            await pre_page.close()

        # -------- Post-trade --------
        if page.url != "https://www.gettex.de/handel/delayed-data/":
            await page.goto("https://www.gettex.de/handel/delayed-data/")

        posttrade_link = page.get_by_role(
            "link", name=re.compile(r"MiFID II verzögerte post-", re.I)
        )
        post_page = await self._open_data_window(page, posttrade_link)
        await self._download_every_link(
            post_page,
            pattern=r"^posttrade\.",
            subdir="munich/posttrade",
        )
        if post_page is not page:
            await post_page.close()

        await page.close()
