# german_scraper/exchanges/berlin_cron.py
"""
Berlin Exchange Scraper – Cron/Batch Friendly Version

- Downloads up to MAX_FILES_PER_RUN new files per run (batching).
- Deduplication handled by pipeline manifest (no duplicate downloads).
- Designed for use with cron or task scheduler: run every N minutes.
- Keeps per-download random delays to mimic human behavior.
- No endless loops or internal sleep; scheduling is handled externally.

USAGE:
    # Schedule with cron (every 15 minutes, for example):
    # */15 * * * * /path/to/your/venv/bin/python -m german_scraper.exchanges.berlin_cron
"""

import re, asyncio
from .base import Exchange
from german_scraper.core.utils import click_first_consent
from german_scraper.core.throttle import random_delay

PRE_URL  = "https://www.boerse-berlin.com/index.php/MiFid_2_Information/Pretrades"
POST_URL = "https://www.boerse-berlin.com/index.php/MiFid_2_Information/Post_Trade"

# ─── batch parameters ─────────────────────────────────────────
MAX_FILES_PER_RUN = 50    # How many new files to download per run (change as needed)
# ──────────────────────────────────────────────────────────────

class BerlinCron(Exchange):
    name = "Börse Berlin (cron/batch)"

    async def _process(
        self, page, url, regex, sub,
        use_href_csv=False, use_type_attr=False
    ):
        await page.goto(url)
        await click_first_consent(page)

        # wait until at least one download anchor is present
        sel = ("a[type='text/comma-separated-values']" if use_type_attr
               else "a[href$='.csv']" if use_href_csv
               else "a")
        await page.wait_for_selector(sel, timeout=15_000)

        # collect anchors
        if use_type_attr:
            links = await page.locator("a[type='text/comma-separated-values']").all()
        elif use_href_csv:
            links = await page.locator("a[href$='.csv']").all()
        else:
            links = await page.locator("a").filter(has_text=re.compile(regex, re.I)).all()

        print(f"🔍 {self.name}: {len(links)} links on {url}")

        downloaded_this_run = 0
        for i, link in enumerate(links, 1):
            text = (await link.text_content()).strip()

            # Stop after batch limit
            if downloaded_this_run >= MAX_FILES_PER_RUN:
                print(f"🛑 Reached batch limit ({MAX_FILES_PER_RUN}).")
                break

            # Debug mode: simulate download
            if self.debug:
                print(f"(DEBUG) [{i}/{len(links)}] Would download: {text}")
                await random_delay(1, 3)
                continue

            # Skip already-downloaded files
            if self.pipeline.has_seen(text):
                print(f"(SKIP) [{i}/{len(links)}] Already downloaded: {text}")
                continue

            # Actual download
            print(f"⬇️  [{i}/{len(links)}] Downloading: {text}")
            try:
                async with page.expect_download() as dl_info:
                    await link.click()
                download = await dl_info.value
                await self.pipeline.save(download, sub)
                downloaded_this_run += 1
                await random_delay(2, 6)    # Human-like delay
            except Exception as e:
                print(f"❌ Failed [{i}] {text}: {e}")
                await random_delay(6, 12)

    async def run(self):
        page = await self.browser.new_page()

        # Pre-trade
        await self._process(
            page, PRE_URL,
            r"^Download der Pretrade Daten für ",
            "berlin/pretrade"
        )

        # Post-trade (anchors identified by MIME type)
        await self._process(
            page, POST_URL,
            r"", "berlin/posttrade",
            use_type_attr=True
        )

        await page.close()
