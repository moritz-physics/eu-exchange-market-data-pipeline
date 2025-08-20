# german_scraper/core/email_inbox.py
"""
IMAP polling helper to fetch LuxSE download links from email.

Usage (async-friendly):
    url = await wait_for_link(
        imap_host=os.getenv("IMAP_HOST", "imap.gmail.com"),
        imap_user=os.getenv("IMAP_USER"),
        imap_pass=os.getenv("IMAP_PASS"),
        from_filter=os.getenv("LUXSE_SENDER", "marketdataservices@bourse.lu"),
        to_filter=os.getenv("LUXSE_TO"),  # optional
        since_epoch=some_timestamp,       # only emails after this
        timeout=300,                      # seconds
        poll_interval=10,                 # seconds
    )
"""

import asyncio, imaplib, email, re, time
from email.header import decode_header
from typing import Optional

LUXSE_LINK_RE = re.compile(r"https://dl\.luxse\.com/dl\?v=[^\s<>\"]+", re.I)

def _search_inbox(
    imap_host: str,
    imap_user: str,
    imap_pass: str,
    from_filter: str,
    to_filter: Optional[str],
    since_epoch: float,
):
    """Blocking IMAP search; returns the newest matching download URL or None."""
    since_date = time.strftime("%d-%b-%Y", time.localtime(since_epoch))
    m = imaplib.IMAP4_SSL(imap_host)
    try:
        m.login(imap_user, imap_pass)
        m.select("INBOX")
        criteria = [f'(FROM "{from_filter}")', f'(SINCE "{since_date}")']
        if to_filter:
            criteria.append(f'(TO "{to_filter}")')

        # Combine criteria
        status, data = m.search(None, *criteria)
        if status != "OK":
            return None

        ids = data[0].split()
        if not ids:
            return None

        # Process newest first
        for msg_id in reversed(ids):
            st, raw = m.fetch(msg_id, "(RFC822)")
            if st != "OK":
                continue
            msg = email.message_from_bytes(raw[0][1])
            # parse both text/plain and text/html
            parts = [msg]
            if msg.is_multipart():
                parts = msg.walk()
            for part in parts:
                ctype = part.get_content_type()
                if ctype in ("text/plain", "text/html"):
                    try:
                        payload = part.get_payload(decode=True) or b""
                        text = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
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
    """
    Poll IMAP for a LuxSE download URL from the given sender (and optional recipient),
    only considering emails AFTER 'since_epoch'. Returns the first URL found or None on timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        url = await asyncio.to_thread(
            _search_inbox,
            imap_host, imap_user, imap_pass, from_filter, to_filter, since_epoch
        )
        if url:
            return url
        await asyncio.sleep(poll_interval)
    return None


# german_scraper/core/email_inbox.py  from here this is for bratislava and might still be unstable
import asyncio, imaplib, email, time
from typing import Optional, Tuple, List

def _search_attachments_since(
    imap_host: str,
    imap_user: str,
    imap_pass: str,
    from_filter: str,
    to_filter: Optional[str],
    since_epoch: float,
) -> Optional[List[Tuple[str, bytes]]]:
    """
    Return list of (filename, data_bytes) for attachments in the newest matching email,
    or None if nothing found yet.
    """
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

        for msg_id in reversed(ids):  # newest first
            st, raw = m.fetch(msg_id, "(RFC822)")
            if st != "OK":
                continue
            msg = email.message_from_bytes(raw[0][1])

            # Collect all attachments from this message
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
    """
    Poll IMAP until we find an email (FROM=from_filter, optional TO=to_filter, SINCE=since_epoch)
    that contains at least one attachment. Returns list of (filename, bytes) or None if timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        res = await asyncio.to_thread(
            _search_attachments_since,
            imap_host, imap_user, imap_pass, from_filter, to_filter, since_epoch
        )
        if res:
            return res
        await asyncio.sleep(poll_interval)
    return None
