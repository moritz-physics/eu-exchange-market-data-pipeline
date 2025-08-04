import random, asyncio
from playwright.async_api import TimeoutError
from .base import Exchange
from german_scraper.core.throttle import random_delay

URLS = [
    ("Prices Tab 2", "https://prices.wienerborse.at/#tab-content2"),
    ("Prices Tab 3", "https://prices.wienerborse.at/#tab-content3"),
    ("Prices Tab 4", "https://prices.wienerborse.at/#tab-content4"),
]

MAX_RELOADS_PER_TAB = 1            # at most one reload if JS didn’t appear
ONCLICK_WAIT_MS      = 15_000      # how long to wait for the onClick() fn

class WienerBoerse(Exchange):
    name = "Wiener Börse"

    async def _trigger_download_via_js(self, page) -> str | None:
        """
        If the page defines a global onClick() that triggers the ZIP download,
        call it via JS and return the file-name hint (link text) if possible.
        Returns None if onClick not found.
        """
        try:
            # wait until the function exists in the page context
            await page.wait_for_function("typeof onClick === 'function'",
                                         timeout=ONCLICK_WAIT_MS)
        except TimeoutError:
            return None

        # call the JS function that would be invoked by the button
        async with page.expect_download() as dl_info:
            await page.evaluate("onClick()")
        download = await dl_info.value
        return download

    async def run(self):
        page = await self.browser.new_page()

        for tab_name, url in URLS:
            print(f"\n🔗 Navigating to {url} ({tab_name})")
            reloads_left = MAX_RELOADS_PER_TAB

            while True:
                await page.goto(url)
                wait_time = random.uniform(5, 8)
                print(f"⏳ Waiting {wait_time:.1f}s for JS to load…")
                await asyncio.sleep(wait_time)

                # try to trigger the download via JS
                download = await self._trigger_download_via_js(page)
                if download:
                    filename = download.suggested_filename
                    label    = f"{tab_name}: {filename}"

                    if self.debug:
                        print(f"(DEBUG) Would download {label}")
                    elif self.pipeline.has_seen(label):
                        print(f"(SKIP) Already have {label}")
                    else:
                        print(f"⬇️  Saving {label}")
                        await self.pipeline.save(download, "wienerboerse")
                    await random_delay(2, 4)
                    break  # success, go to next tab

                # JS not ready → optionally reload once
                if reloads_left:
                    reloads_left -= 1
                    extra_wait = random.uniform(5, 7)
                    print(f"🔄 Reloading once (JS not ready). Waiting {extra_wait:.1f}s…")
                    await asyncio.sleep(extra_wait)
                    continue
                else:
                    print(f"⚠️  Gave up on {tab_name} – onClick() never appeared.")
                    break

        await page.close()
