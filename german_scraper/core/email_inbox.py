"""IMAP polling helpers for exchanges that deliver data via email.

LuxSE returns a download URL, BSSE (Bratislava) returns email attachments.
Both helpers poll an IMAP inbox until a matching message arrives or the
timeout elapses.
"""
from __future__ import annotations

import asyncio
import email
import imaplib
import re
import time
from typing import List, Optional, Tuple

from german_scraper.core.logging_config import get_logger

logger = get_logger(__name__)

LUXSE_LINK_RE: re.Pattern[str] = re.compile(
    r"https://dl\.luxse\.com/dl\?v=[^\s<>\"]+", re.I
)


def _search_inbox(
    imap_host: str,
    imap_user: str,
    imap_pass: str,
    from_filter: str,
    to_filter: Optional[str],
    since_epoch: float,
) -> Optional[str]:
    """Synchronous IMAP search for a LuxSE download URL."""
    since_date = time.strftime("%d-%b-%Y", time.localtime(since_epoch))
    m = imaplib.IMAP4_SSL(imap_host)
    try:
        m.login(imap_user, imap_pass)
        m.select("INBOX")
        criteria = [f'(FROM "{from_filter}")', f'(SINCE "{since_date}")']
        if to_filter:
            criteria.append(f'(TO "{to_filter}")')

        status, data = m.search(None, *criteria)
        if status != "OK":
            return None
        ids = data[0].split()
        if not ids:
            return None

        for msg_id in reversed(ids):
            st, raw = m.fetch(msg_id, "(RFC822)")
            if st != "OK":
                continue
            msg = email.message_from_bytes(raw[0][1])
            parts = list(msg.walk()) if msg.is_multipart() else [msg]
            for part in parts:
                if part.get_content_type() not in ("text/plain", "text/html"):
                    continue
                try:
                    payload = part.get_payload(decode=True) or b""
                    text = payload.decode(
                        part.get_content_charset() or "utf-8", errors="ignore"
                    )
                except Exception:
                    continue
                mobj = LUXSE_LINK_RE.search(text)
                if mobj:
                    return mobj.group(0)
        return None
    finally:
        try:
            m.logout()
        except Exception:
            pass


async def wait_for_link(
    imap_host: str,
    imap_user: str,
    imap_pass: str,
    from_filter: str,
    to_filter: Optional[str],
    since_epoch: float,
    timeout: int = 300,
    poll_interval: int = 10,
) -> Optional[str]:
    """Wait for a LuxSE download URL via IMAP IDLE, falling back to polling.

    IMAP IDLE pushes server-side notifications instead of forcing the
    client to poll on a timer; latency goes from ``poll_interval``
    seconds in the worst case to milliseconds. Gmail and most modern
    IMAP servers support it. If IDLE isn't available (or fails for any
    reason), we fall back to the original polling loop.
    """
    deadline = time.time() + timeout

    # Best-effort IDLE: stop blocking once the server signals new mail
    # or the IDLE turn ends (whichever comes first). One IDLE turn is
    # capped server-side at ~29 minutes; we bound it here at
    # ``poll_interval * 6`` per turn so the polling fallback's pacing
    # is preserved when IDLE is supported but the message hasn't yet
    # arrived.
    async def _idle_turn() -> None:
        def _idle_blocking() -> None:
            m = imaplib.IMAP4_SSL(imap_host)
            try:
                m.login(imap_user, imap_pass)
                m.select("INBOX")
                # imaplib gained .idle() in 3.12; older versions just no-op
                idle = getattr(m, "idle", None)
                if not callable(idle):
                    return
                try:
                    with idle(timeout=poll_interval * 6) as it:
                        # Wait for any update or the timeout.
                        for _ in it:
                            break
                except Exception:
                    return
            finally:
                try:
                    m.logout()
                except Exception:
                    pass
        await asyncio.to_thread(_idle_blocking)

    while time.time() < deadline:
        url = await asyncio.to_thread(
            _search_inbox,
            imap_host, imap_user, imap_pass, from_filter, to_filter, since_epoch,
        )
        if url:
            return url
        # Try push-based wait first; fall back to a fixed sleep if IDLE
        # isn't supported (the function returns immediately).
        try:
            await _idle_turn()
        except Exception:
            await asyncio.sleep(poll_interval)
        else:
            # If IDLE returned quickly (no support / spurious wake), still
            # rate-limit so we don't hammer the search.
            await asyncio.sleep(min(poll_interval, max(deadline - time.time(), 1)))
    logger.warning("wait_for_link timed out after %ds", timeout)
    return None


def _search_attachments_since(
    imap_host: str,
    imap_user: str,
    imap_pass: str,
    from_filter: str,
    to_filter: Optional[str],
    since_epoch: float,
) -> Optional[List[Tuple[str, bytes]]]:
    """Return ``[(filename, bytes), …]`` from the newest matching email."""
    since_date = time.strftime("%d-%b-%Y", time.localtime(since_epoch))
    m = imaplib.IMAP4_SSL(imap_host)
    try:
        m.login(imap_user, imap_pass)
        m.select("INBOX")
        criteria = [f'(FROM "{from_filter}")', f'(SINCE "{since_date}")']
        if to_filter:
            criteria.append(f'(TO "{to_filter}")')

        status, data = m.search(None, *criteria)
        if status != "OK":
            return None
        ids = data[0].split()
        if not ids:
            return None

        for msg_id in reversed(ids):
            st, raw = m.fetch(msg_id, "(RFC822)")
            if st != "OK":
                continue
            msg = email.message_from_bytes(raw[0][1])
            out: List[Tuple[str, bytes]] = []
            for part in msg.walk():
                if part.get_content_disposition() == "attachment":
                    filename = part.get_filename()
                    payload = part.get_payload(decode=True) or b""
                    if filename and payload:
                        out.append((filename, payload))
            if out:
                return out
        return None
    finally:
        try:
            m.logout()
        except Exception:
            pass


async def wait_for_attachments(
    imap_host: str,
    imap_user: str,
    imap_pass: str,
    from_filter: str,
    to_filter: Optional[str],
    since_epoch: float,
    timeout: int = 600,
    poll_interval: int = 10,
) -> Optional[List[Tuple[str, bytes]]]:
    """Poll IMAP for an email with attachments until found or timeout elapses."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        res = await asyncio.to_thread(
            _search_attachments_since,
            imap_host, imap_user, imap_pass, from_filter, to_filter, since_epoch,
        )
        if res:
            return res
        await asyncio.sleep(poll_interval)
    logger.warning("wait_for_attachments timed out after %ds", timeout)
    return None
