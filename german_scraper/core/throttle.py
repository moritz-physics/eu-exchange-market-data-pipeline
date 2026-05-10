"""Random-delay helpers used between page interactions to mimic human pacing."""
from __future__ import annotations

import asyncio
import random

from german_scraper.core.logging_config import get_logger

logger = get_logger(__name__)


async def random_delay(min_s: float = 1.5, max_s: float = 3.0) -> None:
    """Sleep for a uniformly random number of seconds in ``[min_s, max_s]``."""
    if max_s < min_s:
        min_s, max_s = max_s, min_s
    delay = random.uniform(min_s, max_s)
    logger.debug("Sleeping %.2fs (range %.2f–%.2f)", delay, min_s, max_s)
    await asyncio.sleep(delay)
