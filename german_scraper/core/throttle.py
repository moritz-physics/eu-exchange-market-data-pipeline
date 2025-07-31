import asyncio
import random

async def random_delay(base: float = 1.5, jitter: float = 1.5):
    """
    Wait for a random amount of time between [base, base + jitter] seconds.
    Use this after each download or interaction to mimic human behavior.
    """
    delay = random.uniform(base, base + jitter)
    print(f"⏳ Waiting {delay:.2f} seconds...")
    await asyncio.sleep(delay)
