# german_scraper/core/utils.py
import asyncio, random
async def random_delay(min_s: float, max_s: float):
    await asyncio.sleep(random.uniform(min_s, max_s))

async def click_first_consent(page):
    btn = page.locator("button", has_text=r"Accept|OK|Weiter|Agree|Akzeptieren").first
    if await btn.is_visible():
        await btn.click()
