# german_scraper/exchanges/bratislava.py
"""
Bratislava Stock Exchange (BSSE) – request form → email → save all attachments.

Flow:
1) Open request page
2) Click "New request"
3) Fill required fields (first name, last name, email, date, consent)
4) Submit
5) Poll IMAP for an email from sys@bsse.sk and save every attachment.

Fits your pipeline:
- Uses self.pipeline.has_seen / remember-like logic via label dedupe
- Writes files into downloads/bratislava/
"""

import os
import time
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from playwright.async_api import TimeoutError

from .base import Exchange
from german_scraper.core.throttle import random_delay
from german_scraper.core.email_inbox import wait_for_attachments

# ── CONFIG: edit these in code ────────────────────────────────────────────────
FIRST_NAME       = "Moritz"
LAST_NAME        = "Heidtmann"
RECIPIENT_EMAIL  = "heidtmann.moritz@gmail.com"
SENDER_EMAIL     = "sys@bsse.sk"

IMAP_HOST        = "imap.gmail.com"
IMAP_USER        = "yourgmail@gmail.com"
IMAP_PASS        = "your_app_password_here"

REQUEST_URL      = "https://www.bsse.sk/bcpb/en/sending-pre-trade-and-post-trade-data/"
DOWNLOAD_SUBDIR  = "bratislava"   # under downloads/
# ──────────────────────────────────────────────────────────────────────────────

def _today_str_for_bsse() -> str:
    """
    BSSE date input accepts yyyy/mm/dd cleanly (as your recording showed).
    Adjust if you find they changed the format.
    """
    return datetime.now(timezone.utc).strftime("%Y/%m/%d")

class Bratislava(Exchange):
    name = "Bratislava Stock Exchange (BSSE)"

    async def _open_form(self, page):
        # Navigate and click "New request"
        await page.goto(REQUEST_URL)
        # Some sites have transient cookie banners, handle gently if present
        try:
            btn = page.get_by_role("button", name="Accept")
            if await btn.is_visible():
                await btn.click()
        except Exception:
            pass

        await page.get_by_role("link", name="New request").click()

    async def _fill_and_submit(self, page):
        # First name, last name, email
        await page.locator("#fname").fill(FIRST_NAME)
        await page.locator("#lname").fill(LAST_NAME)
        await page.locator("#mail").fill(RECIPIENT_EMAIL)

        # Date (use a clean direct fill, simpler than clicking the calendar widget)
        await page.locator("#date").fill(_today_str_for_bsse())

        # Consent checkbox
        await page.locator("#agree-checkbox").check()

        # Submit
        await page.get_by_role("button", name="Send request").click()

    async def _save_attachment(self, filename: str, data: bytes) -> str:
        """
        Save bytes into downloads/bratislava/ and register dedupe label.
        Returns the saved path.
        """
        base_dir = Path("downloads") / DOWNLOAD_SUBDIR
        base_dir.mkdir(parents=True, exist_ok=True)

        target = base_dir / filename
        label  = f"BSSE:{filename}"

        if self.pipeline.has_seen(label):
            print(f"(SKIP) Already saved {filename}")
            return str(target)

        if not target.exists():
            target.write_bytes(data)
            print(f"⬇️  Saved → {target}")
        else:
            print(f"(SKIP) File already on disk: {target}")

        # If your pipeline supports remembering arbitrary labels:
        remember = getattr(self.pipeline, "remember", None)
        if callable(remember):
            remember(label)

        return str(target)

    async def run(self):
        # Phase 1: submit request
        page = await self.browser.new_page()
        await self._open_form(page)
        await self._fill_and_submit(page)

        # tiny human-like wait
        await random_delay(1.0, 2.0)

        # Phase 2: poll mailbox for attachments since now
        since_ts = time.time()
        print(f"📬 Waiting for email to {RECIPIENT_EMAIL} from {SENDER_EMAIL} with attachments …")
        attachments = await wait_for_attachments(
            imap_host=IMAP_HOST,
            imap_user=IMAP_USER,
            imap_pass=IMAP_PASS,
            from_filter=SENDER_EMAIL,
            to_filter=RECIPIENT_EMAIL,
            since_epoch=since_ts,
            timeout=600,          # up to 10 minutes; adjust if BSSE is slow
            poll_interval=10,
        )

        if not attachments:
            raise TimeoutError("Timed out waiting for BSSE email with attachments")

        print(f"📎 Received {len(attachments)} attachment(s). Saving…")
        for (fname, blob) in attachments:
            # Defensive: strip path separators from filename
            safe_name = os.path.basename(fname)
            await self._save_attachment(safe_name, blob)
            await random_delay(0.3, 0.8)

        await page.close()
        print("✅ BSSE done.")
