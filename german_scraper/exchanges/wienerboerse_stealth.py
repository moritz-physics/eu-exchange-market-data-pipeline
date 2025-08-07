"""
Wiener Börse scraper with stealth and human-like behaviour.

Uses:
  - playwright-stealth  -> masks automation fingerprints
  - random mouse moves  -> lowers bot-score
  - gentle scrolling    -> simulates reading
Keeps your original JS onClick download trigger, batching, and manifest.
"""

import random, asyncio, math
from playwright.async_api import TimeoutError

from playwright_stealth import stealth_async
from .base import Exchange
from german_scraper.core.throttle import random_delay

URLS = [
    ("Prices Tab 2", "https://prices.wienerborse.at/#tab-content2"),
    ("Prices Tab 3", "https://prices.wienerborse.at/#tab-content3"),
    ("Prices Tab 4", "https://prices.wienerborse.at/#tab-content4"),
]

MAX_RELOADS_PER_TAB = 1
ONCLICK_WAIT_MS     = 15_000

# ───────────────────────── helper: human mouse ──────────────────────────
async def human_mouse_move(page, steps: int = 25):
    """
    Move the mouse in a gentle curve across the viewport.
    """
    vp = page.viewport_size or {"width": 1280, "height": 720}
    start_x = random.randint(0, vp["width"] // 3)
    start_y = random.randint(0, vp["height"] // 3)
    end_x   = random.randint(vp["width"] // 2, vp["width"] - 1)
    end_y   = random.randint(vp["height"] // 2, vp["height"] - 1)

    for i in range(steps + 1):
        t = i / steps
        # ease-in-out curve
        t = 0.5 * (1 - math.cos(math.pi * t))
        x = int(start_x + (end_x - start_x) * t)
        y = int(start_y + (end_y - start_y) * t)
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.01, 0.03))

# ───────────────────────────────── scraper ───────────────────────────────
class WienerBoerseStealth(Exchange):
    name = "Wiener Börse (stealth)"

    async def _trigger_download_via_js(self, page):
        try:
            await page.wait_for_function("typeof onClick === 'function'",
                                         timeout=ONCLICK_WAIT_MS)
        except TimeoutError:
            return None
        async with page.expect_download() as dl_info:
            await page.evaluate("onClick()")
        return await dl_info.value

    async def run(self):
        # create a fresh context with stealth fingerprints
        context = await self.browser.new_context(
            locale="de-AT",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
        )
        await stealth_async(context)          # ← masks automation
        page = await context.new_page()

        for tab_name, url in URLS:
            print(f"\n🔗 Navigating to {url} ({tab_name})")
            reloads_left = MAX_RELOADS_PER_TAB

            while True:
                await page.goto(url, wait_until="domcontentloaded")

                # simulate reading / settling
                await human_mouse_move(page)
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight/3)")
                await asyncio.sleep(random.uniform(4, 6))

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
                    break

                # JS not ready → optionally reload once
                if reloads_left:
                    reloads_left -= 1
                    extra_wait = random.uniform(5, 8)
                    print(f"🔄 Reloading once (JS not ready). Waiting {extra_wait:.1f}s…")
                    await asyncio.sleep(extra_wait)
                    continue
                else:
                    print(f"⚠️  Gave up on {tab_name} – onClick() never appeared.")
                    break

        await page.close()
        await context.close()
