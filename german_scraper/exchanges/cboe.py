# german_scraper/exchanges/cboe.py

import re
import asyncio
from .base import Exchange
from german_scraper.core.throttle import random_delay

CBOE_URL = "https://www.cboe.com/europe/equities/trade_data/"
MARKETS = ["bxe", "cxe", "dxe", "apa"]

class Cboe(Exchange):
    name = "Cboe Europe"

    async def dismiss_cookie_banner(self, page, timeout=5):
        """
        Wait up to `timeout` seconds for the "Accept All" cookie button to appear, then click it.
        """
        try:
            await asyncio.sleep(2)  # Give the banner a moment to pop up
            for _ in range(timeout * 2):  # Check every 0.5s up to `timeout`
                btn = page.get_by_role("button", name=re.compile(r"Accept All", re.I))
                if await btn.is_visible():
                    print("🍪 Accepting cookies via 'Accept All' button")
                    await btn.click()
                    await page.wait_for_timeout(400)
                    return
                await asyncio.sleep(0.5)
            print("⚠️  Cookie banner not found within timeout")
        except Exception as e:
            print(f"⚠️  Failed to dismiss cookie banner: {e}")

    async def run(self):
        page = await self.browser.new_page()
        await page.goto(CBOE_URL)

        await self.dismiss_cookie_banner(page)  # Handle the cookie banner

        print("🔍 Looking for all hourly .csv files on Cboe Europe page...")

        total_found = 0
        for market in MARKETS:
            # Section titles are like: "B XE - HOURLY FILES"
            section_heading = f"{market.upper()} - HOURLY FILES"
            # Find all .csv links for this market and hourly pattern
            csv_links = await page.locator(f"a[href$='.csv']").all()
            # Only links matching pattern: rts13_public_trade_data_{market}_YYYY-MM-DD_HH.csv
            market_csvs = []
            pattern = re.compile(rf"rts13_public_trade_data_{market}_\d{{4}}-\d{{2}}-\d{{2}}_\d{{2}}\.csv$", re.I)
            for link in csv_links:
                href = await link.get_attribute("href")
                if href and pattern.search(href):
                    market_csvs.append((link, href))

            print(f"🗂 {market.upper()} hourly files: {len(market_csvs)} found")
            total_found += len(market_csvs)

            for idx, (link, href) in enumerate(market_csvs, 1):
                filename = href.split("/")[-1]
                print(f"  [{idx}/{len(market_csvs)}] {filename}")

                if self.debug:
                    print(f"   (DEBUG) Would download {filename}")
                    await random_delay(0.3, 1.2)
                    continue
                if self.pipeline.has_seen(filename):
                    print(f"   (SKIP) Already downloaded: {filename}")
                    continue

                # Download with Playwright for simplicity and consistency
                async with page.expect_download() as dl_info:
                    await link.click()
                download = await dl_info.value
                await self.pipeline.save(download, f"cboe/{market}/hourly")
                await random_delay(0.5, 2.5)

        print(f"✅ Done. Total hourly files found: {total_found}")
        await page.close()
