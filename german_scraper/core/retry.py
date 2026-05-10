"""Async retry helper with exponential backoff and jitter.

Used for transient failures — network hiccups, slow page loads, intermittent
download timeouts. Keeps a single retry policy across scrapers so we don't
sprinkle ad-hoc try/except + sleep blocks throughout the codebase.
"""
from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, Iterable, TypeVar

from german_scraper.core.logging_config import get_logger

T = TypeVar("T")

logger = get_logger(__name__)


async def with_retry(
    func: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    jitter: float = 0.5,
    retry_on: Iterable[type[BaseException]] = (Exception,),
    label: str = "operation",
) -> T:
    """Run ``func`` up to ``attempts`` times with exponential backoff.

    Args:
        func: Zero-arg async callable to invoke.
        attempts: Total attempts (including the first try).
        base_delay: Initial delay in seconds before the second attempt.
        max_delay: Cap on per-attempt sleep.
        jitter: Random fraction added to each backoff (0 = deterministic).
        retry_on: Exception types that should trigger a retry. Anything else
            propagates immediately.
        label: Short identifier used in log messages.

    Raises:
        The final exception once all attempts have been exhausted.
    """
    last_exc: BaseException | None = None
    retry_tuple = tuple(retry_on)
    for attempt in range(1, attempts + 1):
        try:
            return await func()
        except retry_tuple as exc:
            last_exc = exc
            if attempt >= attempts:
                logger.error("%s failed after %d attempts: %s", label, attempts, exc)
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay += random.uniform(0, jitter * delay)
            logger.warning(
                "%s failed on attempt %d/%d (%s) — retrying in %.1fs",
                label, attempt, attempts, exc, delay,
            )
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc
