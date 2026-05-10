"""Luxembourg Stock Exchange (LuxSE) – pre & post-trade request scraper.

LuxSE delivers data via emailed download links: the scraper fills the
on-site request form, then polls IMAP for the resulting email and
downloads the file. All credentials come from the environment.

Required env vars:
    LUXSE_FIRST_NAME, LUXSE_LAST_NAME, LUXSE_RECIPIENT_EMAIL,
    IMAP_HOST, IMAP_USER, IMAP_PASS
"""
from __future__ import annotations

import os
import re
import time

from playwright.async_api import Page, TimeoutError

from .base import Exchange
from german_scraper.core.email_inbox import wait_for_link
from german_scraper.core.throttle import random_delay

LUXSE_URL: str = (
    "https://www.luxse.com/market-overview/trading-data/pre-and-post-trade-data"
)
SENDER_EMAIL: str = os.environ.get(
    "LUXSE_SENDER_EMAIL", "marketdataservices@bourse.lu"
)


class LuxSE(Exchange):
    """LuxSE pre & post-trade request scraper."""

    name: str = "Luxembourg Stock Exchange (LuxSE)"

    def _config(self) -> dict[str, str]:
        """Return required form fields and IMAP creds; raise if missing."""
        env = {
            "first_name": os.environ.get("LUXSE_FIRST_NAME"),
            "last_name": os.environ.get("LUXSE_LAST_NAME"),
            "recipient": os.environ.get("LUXSE_RECIPIENT_EMAIL"),
            "imap_host": os.environ.get("IMAP_HOST", "imap.gmail.com"),
            "imap_user": os.environ.get("IMAP_USER"),
            "imap_pass": os.environ.get("IMAP_PASS"),
        }
        missing = [k for k, v in env.items() if not v]
        if missing:
            raise RuntimeError(
                f"LuxSE requires environment variables for: {', '.join(missing)}"
            )
        return env  # type: ignore[return-value]

    async def _accept_cookies(self, page: Page) -> None:
        try:
            btn = page.get_by_role("button", name=re.compile(r"Allow all", re.I))
            if await btn.is_visible():
                await btn.click()
        except Exception:
            pass

    async def _fill_form_and_submit(
        self, page: Page, section_label: str, cfg: dict[str, str]
    ) -> None:
        """Open the matching accordion and submit the request form."""
        await page.locator("div").filter(has_text=re.compile(section_label)).first.click()

        await page.locator("div", has_text=re.compile(r"^Name \*$")).get_by_role(
            "textbox"
        ).fill(cfg["first_name"])
        await page.locator("div", has_text=re.compile(r"^Last name \*$")).get_by_role(
            "textbox"
        ).fill(cfg["last_name"])
        await page.locator("div", has_text=re.compile(r"^E-mail \*$")).get_by_role(
            "textbox"
        ).fill(cfg["recipient"])

        try:
            cb = page.get_by_role("checkbox")
            if await cb.count() > 0:
                await cb.first.check()
            else:
                await page.get_by_role("paragraph").filter(
                    has_text=re.compile(r"By completing this form", re.I)
                ).locator("svg").click()
        except Exception as exc:
            self.logger.warning("Could not toggle consent checkbox: %s", exc)

        await page.get_by_role(
            "button", name=re.compile(r"Send your request", re.I)
        ).click()

    async def _wait_email_and_download(
        self, page: Page, subdir: str, since_epoch: float, cfg: dict[str, str]
    ) -> None:
        """Block on IMAP for the LuxSE link, then trigger a Playwright download."""
        self.logger.info(
            "Waiting for LuxSE email to %s from %s", cfg["recipient"], SENDER_EMAIL,
        )
        url = await wait_for_link(
            imap_host=cfg["imap_host"],
            imap_user=cfg["imap_user"],
            imap_pass=cfg["imap_pass"],
            from_filter=SENDER_EMAIL,
            to_filter=cfg["recipient"],
            since_epoch=since_epoch,
            timeout=300,
            poll_interval=10,
        )
        if not url:
            raise TimeoutError("Timed out waiting for LuxSE email")
        self.logger.info("Got download link: %s", url)

        label = f"LuxSE {subdir}: {url}"
        if self.debug:
            self.logger.info("(DEBUG) Would download: %s", label)
            return
        if self.pipeline.has_seen(label):
            self.logger.info("(SKIP) Already downloaded: %s", label)
            return

        async with page.expect_download() as dl_info:
            await page.evaluate(
                """
                (href) => {
                    const a = document.createElement('a');
                    a.href = href;
                    a.download = '';
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                }
                """,
                url,
            )
        download = await dl_info.value
        await self.pipeline.save(download, f"luxse/{subdir}")
        self.pipeline.mark_seen(label)

    async def run(self) -> None:
        """Submit pre-trade then post-trade requests and download both files."""
        cfg = self._config()
        page = await self.browser.new_page()
        try:
            await page.goto(LUXSE_URL)
            await self._accept_cookies(page)

            pre_since = time.time()
            await self._fill_form_and_submit(page, r"^Pre-trade data$", cfg)
            await random_delay(1.0, 2.0)
            await self._wait_email_and_download(page, "pre", pre_since, cfg)

            post_since = time.time()
            await self._fill_form_and_submit(page, r"^Post-trade data$", cfg)
            await random_delay(1.0, 2.0)
            await self._wait_email_and_download(page, "post", post_since, cfg)
        finally:
            await page.close()
