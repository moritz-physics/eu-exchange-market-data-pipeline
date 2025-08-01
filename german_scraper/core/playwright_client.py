# german_scraper/core/playwright_client.py
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright

class PlaywrightClient:
    """Launch one Chromium instance and share it with all scrapers."""
    @asynccontextmanager
    async def launch(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)  # Set headless=True for production
            # browser = await p.chromium.launch(headless=True)  # Use Chromium if preferred
            # browser = await p.webkit.launch(headless=True)  # Use WebKit if preferred
            try:
                yield browser
            finally:
                await browser.close()
