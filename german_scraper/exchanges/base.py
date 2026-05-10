"""Abstract base class shared by every exchange scraper."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from playwright.async_api import Browser, Locator, Page

from german_scraper.core.logging_config import get_logger
from german_scraper.core.retry import with_retry
from german_scraper.core.throttle import random_delay

if TYPE_CHECKING:
    from german_scraper.pipelines.save_local import SaveLocalPipeline


class Exchange(ABC):
    """Common interface and helpers for every exchange scraper.

    Subclasses set a ``name`` class attribute and implement :meth:`run`.
    They get a configured logger, a shared pipeline, and ready-made helpers
    for the most common interaction pattern: click a link, expect a download,
    save it via the pipeline.
    """

    name: str = "Unnamed Exchange"

    def __init__(
        self,
        browser: Browser,
        pipeline: "SaveLocalPipeline",
        debug: bool = True,
    ) -> None:
        self.browser = browser
        self.pipeline = pipeline
        self.debug = debug
        self.logger = get_logger(f"scraper.{self.__class__.__name__}")

    @abstractmethod
    async def run(self) -> None:
        """Execute the scrape end-to-end."""

    async def _download_via_click(
        self,
        page: Page,
        clickable: Locator,
        subdir: str,
        label: str,
        *,
        post_delay: tuple[float, float] = (0.5, 1.5),
        attempts: int = 3,
    ) -> bool:
        """Click ``clickable`` to trigger a download and pass it to the pipeline.

        Honours ``self.debug`` (dry-run logs only), the manifest dedupe, and
        wraps the click+save in :func:`with_retry` for transient failures.

        Returns ``True`` if a new file was saved, ``False`` for skip/dry-run.
        """
        if self.debug:
            self.logger.info("(DEBUG) Would download: %s", label)
            await random_delay(*post_delay)
            return False

        if self.pipeline.has_seen(label):
            self.logger.info("(SKIP) Already downloaded: %s", label)
            return False

        async def _do_click_and_save() -> bool:
            self.logger.info("Downloading: %s", label)
            async with page.expect_download() as dl_info:
                await clickable.click()
            download = await dl_info.value
            await self.pipeline.save(download, subdir)
            return True

        try:
            saved = await with_retry(
                _do_click_and_save,
                attempts=attempts,
                base_delay=2.0,
                max_delay=15.0,
                label=f"download[{label}]",
            )
        except Exception as exc:
            self.logger.error("Failed to download %s: %s", label, exc)
            return False

        await random_delay(*post_delay)
        return saved
