"""Bratislava Stock Exchange (BSSE) – request form → email → save attachments.

Submits the BSSE request form, then polls IMAP for an email from
``sys@bsse.sk`` and saves every attachment to the local pipeline.

Required env vars:
    BSSE_FIRST_NAME, BSSE_LAST_NAME, BSSE_RECIPIENT_EMAIL,
    IMAP_HOST, IMAP_USER, IMAP_PASS
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from playwright.async_api import Page, TimeoutError

from .base import Exchange
from german_scraper.core.email_inbox import wait_for_attachments
from german_scraper.core.throttle import random_delay
from german_scraper.settings import SETTINGS

REQUEST_URL: str = SETTINGS.exchange_url(
    "bratislava",
    "https://www.bsse.sk/bcpb/en/sending-pre-trade-and-post-trade-data/",
)
DOWNLOAD_SUBDIR: str = "bratislava"
SENDER_EMAIL: str = os.environ.get("BSSE_SENDER_EMAIL", "sys@bsse.sk")


def _today_str_for_bsse() -> str:
    """BSSE's date input expects ``yyyy/mm/dd``."""
    return datetime.now(timezone.utc).strftime("%Y/%m/%d")


class Bratislava(Exchange):
    """Bratislava Stock Exchange (BSSE) request-and-email scraper."""

    name: str = "Bratislava Stock Exchange (BSSE)"

    def _config(self) -> dict[str, str]:
        env = {
            "first_name": os.environ.get("BSSE_FIRST_NAME"),
            "last_name": os.environ.get("BSSE_LAST_NAME"),
            "recipient": os.environ.get("BSSE_RECIPIENT_EMAIL"),
            "imap_host": os.environ.get("IMAP_HOST", "imap.gmail.com"),
            "imap_user": os.environ.get("IMAP_USER"),
            "imap_pass": os.environ.get("IMAP_PASS"),
        }
        missing = [k for k, v in env.items() if not v]
        if missing:
            raise RuntimeError(
                f"Bratislava requires environment variables for: {', '.join(missing)}"
            )
        return env  # type: ignore[return-value]

    async def _open_form(self, page: Page) -> None:
        """Navigate to the request page and click 'New request'."""
        await page.goto(REQUEST_URL)
        try:
            btn = page.get_by_role("button", name="Accept")
            if await btn.is_visible():
                await btn.click()
        except Exception:
            pass
        await page.get_by_role("link", name="New request").click()

    async def _fill_and_submit(self, page: Page, cfg: dict[str, str]) -> None:
        """Fill the form and click 'Send request'."""
        await page.locator("#fname").fill(cfg["first_name"])
        await page.locator("#lname").fill(cfg["last_name"])
        await page.locator("#mail").fill(cfg["recipient"])
        await page.locator("#date").fill(_today_str_for_bsse())
        await page.locator("#agree-checkbox").check()
        await page.get_by_role("button", name="Send request").click()

    async def run(self) -> None:
        """Submit the form, poll IMAP, persist every attachment."""
        cfg = self._config()
        page = await self.browser.new_page()
        try:
            await self._open_form(page)
            await self._fill_and_submit(page, cfg)
            await random_delay(1.0, 2.0)

            since_ts = time.time()
            self.logger.info(
                "Waiting for email to %s from %s with attachments",
                cfg["recipient"], SENDER_EMAIL,
            )
            attachments = await wait_for_attachments(
                imap_host=cfg["imap_host"],
                imap_user=cfg["imap_user"],
                imap_pass=cfg["imap_pass"],
                from_filter=SENDER_EMAIL,
                to_filter=cfg["recipient"],
                since_epoch=since_ts,
                timeout=600,
                poll_interval=10,
            )
            if not attachments:
                raise TimeoutError("Timed out waiting for BSSE email with attachments")

            self.logger.info("Received %d attachment(s)", len(attachments))
            for fname, blob in attachments:
                safe_name = os.path.basename(fname)
                await self.pipeline.save((safe_name, blob), DOWNLOAD_SUBDIR)
                await random_delay(0.3, 0.8)
        finally:
            await page.close()
        self.logger.info("BSSE done")
