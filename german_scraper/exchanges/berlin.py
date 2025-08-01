# german_scraper/exchanges/berlin.py
import re, asyncio
from .base import Exchange
from german_scraper.core.utils import click_first_consent
from german_scraper.core.throttle import random_delay

PRE_URL  = "https://www.boerse-berlin.com/index.php/MiFid_2_Information/Pretrades"
POST_URL = "https://www.boerse-berlin.com/index.php/MiFid_2_Information/Post_Trade"

class Berlin(Exchange):
    name = "Börse Berlin"

    async def _process(
        self, page, url, regex, sub,
        use_href_csv=False, use_type_attr=False
    ):
        await page.goto(url)
        await click_first_consent(page)

        # --- wait until the table with links has arrived ---
        try:
            if use_type_attr:
                await page.wait_for_selector(
                    "a[type='text/comma-separated-values']",
                    timeout=15_000
                )
            elif use_href_csv:
                await page.wait_for_selector("a[href$='.csv']", timeout=15_000)
            else:
                # a generic anchor just to be safe
                await page.wait_for_selector("a", timeout=15_000)
        except Exception:
            print(f"⚠️  No download links appeared on {url}")
            return

        # --- collect anchors ---
        if use_type_attr:                       # post-trade (robust)
            links = await page.locator(
                "a[type='text/comma-separated-values']"
            ).all()
        elif use_href_csv:                      # generic .csv locator
            links = await page.locator("a[href$='.csv']").all()
        else:                                   # pre-trade by visible text
            links = await page.locator("a").filter(
                has_text=re.compile(regex, re.I)
            ).all()

        print(f"🔍 {self.name}: {len(links)} links on {url}")

        for i, link in enumerate(links, 1):
            text = (await link.text_content()).strip()

            if self.debug:
                print(f"(DEBUG) [{i}/{len(links)}] Would download: {text}")
                await random_delay(0.01, 0.03)
                continue

            if self.pipeline.has_seen(text):
                print(f"(SKIP) [{i}/{len(links)}] Already downloaded: {text}")
                continue

            print(f"⬇️  [{i}/{len(links)}] Downloading: {text}")
            try:
                async with page.expect_download() as dl_info:
                    await link.click()
                download = await dl_info.value          # **await** here
                await self.pipeline.save(download, sub)
                await random_delay(0.8, 2.2)
            except Exception as e:
                print(f"❌ Failed on [{i}] {text}: {e}")
                await random_delay(4, 8)

    async def run(self):
        page = await self.browser.new_page()

        # 1️⃣ Pre-trade – match by visible link text
        await self._process(
            page, PRE_URL,
            r"^Download der Pretrade Daten für ",
            "berlin/pretrade"
        )

        # 2️⃣ Post-trade – wait for anchors and match by `type` attribute
        await self._process(
            page, POST_URL,
            r"",                             # not used
            "berlin/posttrade",
            use_type_attr=True               # <—
        )

        await page.close()
