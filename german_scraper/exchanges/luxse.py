# german_scraper/exchanges/luxse.py
"""
Luxembourg Stock Exchange (LuxSE) – Pre & Post trade request + email download.

This variant uses IN-CODE settings (no environment variables).
Edit the CONFIG section below with your details.
"""

import time, re
from playwright.async_api import TimeoutError
from .base import Exchange
from german_scraper.core.throttle import random_delay
from german_scraper.core.email_inbox import wait_for_link

# ── CONFIG: edit these ────────────────────────────────────────────────────────
FIRST_NAME       = "Moritz"
LAST_NAME        = "Heidtmann"
RECIPIENT_EMAIL  = "heidtmann.moritz@gmail.com"       # where LuxSE sends the links
SENDER_EMAIL     = "marketdataservices@bourse.lu"     # LuxSE sender to match

IMAP_HOST        = "imap.gmail.com"                   # your IMAP host
IMAP_USER        = "yourgmail@gmail.com"              # your IMAP username (full email)
IMAP_PASS        = "your_app_password_here"           # IMAP/app password (NOT your login pw)
# ──────────────────────────────────────────────────────────────────────────────

LUXSE_URL = "https://www.luxse.com/market-overview/trading-data/pre-and-post-trade-data"

class LuxSE(Exchange):
    name = "Luxembourg Stock Exchange (LuxSE)"

    async def _accept_cookies(self, page):
        # OneTrust-style button
        try:
            btn = page.get_by_role("button", name=re.compile(r"Allow all", re.I))
            if await btn.is_visible():
                await btn.click()
        except Exception:
            pass

    async def _fill_form_and_submit(self, page, section_label: str):
        """
        section_label: r"^Pre-trade data$" or r"^Post-trade data$"
        """
        # open the accordion/tab
        await page.locator("div").filter(has_text=re.compile(section_label)).first.click()

        # Fill required fields
        await page.locator("div", has_text=re.compile(r"^Name \*$")).get_by_role("textbox").fill(FIRST_NAME)
        await page.locator("div", has_text=re.compile(r"^Last name \*$")).get_by_role("textbox").fill(LAST_NAME)
        await page.locator("div", has_text=re.compile(r"^E-mail \*$")).get_by_role("textbox").fill(RECIPIENT_EMAIL)

        # Consent checkbox or its label
        try:
            cb = page.get_by_role("checkbox")
            if await cb.count() > 0:
                await cb.first.check()
            else:
                await page.get_by_role("paragraph").filter(
                    has_text=re.compile(r"By completing this form", re.I)
                ).locator("svg").click()
        except Exception:
            pass

        # Submit
        await page.get_by_role("button", name=re.compile(r"Send your request", re.I)).click()

    async def _wait_email_and_download(self, page, subdir: str, since_epoch: float):
        if not (IMAP_USER and IMAP_PASS):
            raise RuntimeError(
                "IMAP_USER/IMAP_PASS not set in luxse.py CONFIG section."
            )

        print(f"📬 Waiting for LuxSE email → {RECIPIENT_EMAIL} from {SENDER_EMAIL} …")
        url = await wait_for_link(
            imap_host=IMAP_HOST,
            imap_user=IMAP_USER,
            imap_pass=IMAP_PASS,
            from_filter=SENDER_EMAIL,
            to_filter=RECIPIENT_EMAIL,
            since_epoch=since_epoch,
            timeout=300,
            poll_interval=10,
        )
        if not url:
            raise TimeoutError("Timed out waiting for LuxSE email with download link")
        print(f"🔗 Got download link: {url}")

        label = f"LuxSE {subdir}: {url}"
        if self.debug:
            print(f"(DEBUG) Would download: {label}")
            return
        if self.pipeline.has_seen(label):
            print(f"(SKIP) Already downloaded: {label}")
            return

        # Trigger a download event via a temporary anchor (so pipeline .save() works)
        async with page.expect_download() as dl_info:
            await page.evaluate("""
                (href) => {
                    const a = document.createElement('a');
                    a.href = href;
                    a.download = '';
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                }
            """, url)
        download = await dl_info.value
        await self.pipeline.save(download, f"luxse/{subdir}")

    async def run(self):
        page = await self.browser.new_page()
        await page.goto(LUXSE_URL)
        await self._accept_cookies(page)

        # PRE-TRADE
        pre_since = time.time()
        await self._fill_form_and_submit(page, r"^Pre-trade data$")
        await random_delay(1.0, 2.0)
        await self._wait_email_and_download(page, "pre", pre_since)

        # POST-TRADE
        post_since = time.time()
        await self._fill_form_and_submit(page, r"^Post-trade data$")
        await random_delay(1.0, 2.0)
        await self._wait_email_and_download(page, "post", post_since)

        await page.close()
