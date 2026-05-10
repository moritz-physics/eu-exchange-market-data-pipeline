"""Wiener Börse scraper with stealth and human-like behaviour.

Adds:
  * playwright-stealth fingerprint masking
  * random mouse moves and gentle scrolling
to lower the probability of triggering reCAPTCHA on Wiener Börse.
"""
from __future__ import annotations

import asyncio
import math
import random

from playwright.async_api import Page, TimeoutError

from .base import Exchange
from german_scraper.core.throttle import random_delay

URLS: list[tuple[str, str]] = [
    ("Prices Tab 2", "https://prices.wienerborse.at/#tab-content2"),
    ("Prices Tab 3", "https://prices.wienerborse.at/#tab-content3"),
    ("Prices Tab 4", "https://prices.wienerborse.at/#tab-content4"),
]

MAX_RELOADS_PER_TAB: int = 1
ONCLICK_WAIT_MS: int = 15_000


async def human_mouse_move(page: Page, steps: int = 25) -> None:
    """Move the mouse along a smooth ease-in-out curve across the viewport."""
    vp = page.viewport_size or {"width": 1280, "height": 720}
    start_x = random.randint(0, vp["width"] // 3)
    start_y = random.randint(0, vp["height"] // 3)
    end_x = random.randint(vp["width"] // 2, vp["width"] - 1)
    end_y = random.randint(vp["height"] // 2, vp["height"] - 1)

    for i in range(steps + 1):
        t = i / steps
        t = 0.5 * (1 - math.cos(math.pi * t))
        x = int(start_x + (end_x - start_x) * t)
        y = int(start_y + (end_y - start_y) * t)
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.01, 0.03))


class WienerBoerseStealth(Exchange):
    """Wiener Börse pre-trade scraper with stealth fingerprints."""

    name: str = "Wiener Börse (stealth)"

    async def _trigger_download_via_js(self, page: Page):
        """Invoke the page's ``onClick()`` function and capture the download."""
        try:
            await page.wait_for_function(
                "typeof onClick === 'function'", timeout=ONCLICK_WAIT_MS,
            )
        except TimeoutError:
            return None
        async with page.expect_download() as dl_info:
            await page.evaluate("onClick()")
        return await dl_info.value

    async def run(self) -> None:
        """Run the three Wiener Börse tabs inside a stealth-cloaked context."""
        context = await self.browser.new_context(
            locale="de-AT",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
        )
        # playwright-stealth's API has shifted between versions; import lazily
        # and degrade gracefully if it's missing.
        try:
            from playwright_stealth import stealth_async  # type: ignore
            await stealth_async(context)
        except ImportError:
            try:
                from playwright_stealth import Stealth  # type: ignore
                await Stealth().apply_stealth_async(context)
            except Exception as exc:
                self.logger.warning(
                    "playwright-stealth unavailable; running without stealth: %s", exc,
                )
        page = await context.new_page()

        try:
            for tab_name, url in URLS:
                self.logger.info("Navigating to %s (%s)", url, tab_name)
                reloads_left = MAX_RELOADS_PER_TAB

                while True:
                    await page.goto(url, wait_until="domcontentloaded")
                    await human_mouse_move(page)
                    await page.evaluate(
                        "window.scrollBy(0, document.body.scrollHeight/3)"
                    )
                    await asyncio.sleep(random.uniform(4, 6))

                    download = await self._trigger_download_via_js(page)
                    if download:
                        filename = download.suggested_filename
                        label = f"{tab_name}: {filename}"
                        if self.debug:
                            self.logger.info("(DEBUG) Would download %s", label)
                        elif self.pipeline.has_seen(label):
                            self.logger.info("(SKIP) Already have %s", label)
                        else:
                            self.logger.info("Saving %s", label)
                            await self.pipeline.save(download, "wienerboerse")
                        await random_delay(2, 4)
                        break

                    if reloads_left:
                        reloads_left -= 1
                        extra_wait = random.uniform(5, 8)
                        self.logger.warning(
                            "Reloading once (JS not ready). Waiting %.1fs", extra_wait,
                        )
                        await asyncio.sleep(extra_wait)
                        continue
                    self.logger.error("Gave up on %s", tab_name)
                    break
        finally:
            await page.close()
            await context.close()
