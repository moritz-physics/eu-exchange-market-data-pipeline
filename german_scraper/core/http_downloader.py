"""HTTP download helper that piggybacks Playwright's cookies.

Many venues expose downloads as plain ``<a href="…csv">`` anchors. For
those we don't need a browser at all — once Playwright has accepted the
cookie banner, we can copy the cookies to ``aiohttp`` and stream the
file via a single HTTP GET. That's roughly 10× faster than
``page.expect_download()`` and unloads the browser for other work.

The helper:
    * uses the same User-Agent as the page (so referer + cookies match);
    * copies all cookies from the active Playwright context into an
      ``aiohttp.CookieJar``;
    * streams the response into memory and returns ``(filename, bytes)``,
      which the existing ``SaveLocalPipeline.save`` accepts as-is.

If a venue gates downloads behind JavaScript, request signing, or a
session token that isn't in cookies, fall back to the original
``page.expect_download()`` flow.
"""
from __future__ import annotations

import asyncio
from typing import Optional
from urllib.parse import urlparse, urlsplit, urlunsplit

import aiohttp
from playwright.async_api import BrowserContext, Page

from german_scraper.core.logging_config import get_logger
from german_scraper.core.retry import with_retry

logger = get_logger(__name__)


def _filename_from_url(url: str, fallback: str = "download.bin") -> str:
    """Best-effort: take the last non-empty path segment, strip query."""
    parsed = urlsplit(url)
    parts = [p for p in parsed.path.split("/") if p]
    return parts[-1] if parts else fallback


def _absolute_url(href: str, base: str) -> str:
    """Resolve relative ``href`` against ``base`` if needed."""
    if href.startswith(("http://", "https://")):
        return href
    base_parts = urlsplit(base)
    if href.startswith("//"):
        return f"{base_parts.scheme}:{href}"
    if href.startswith("/"):
        return urlunsplit(
            (base_parts.scheme, base_parts.netloc, href, "", "")
        )
    base_dir = base_parts.path.rsplit("/", 1)[0] + "/"
    return urlunsplit(
        (base_parts.scheme, base_parts.netloc, base_dir + href, "", "")
    )


async def _cookie_jar_from_context(
    context: BrowserContext, target_url: str,
) -> aiohttp.CookieJar:
    """Copy cookies from a Playwright context into an aiohttp jar.

    Filtered to cookies whose domain matches the target URL — sending
    every cookie to every host is both wasteful and a privacy hazard
    when one scraper is reused across venues.
    """
    target_host = urlparse(target_url).netloc.lower()
    jar = aiohttp.CookieJar(unsafe=True)
    cookies = await context.cookies()
    for c in cookies:
        domain = (c.get("domain") or "").lstrip(".").lower()
        if not domain or target_host.endswith(domain):
            jar.update_cookies(
                {c["name"]: c["value"]},
                response_url=aiohttp.helpers.URL(target_url),
            )
    return jar


async def http_download(
    url: str,
    *,
    page: Optional[Page] = None,
    context: Optional[BrowserContext] = None,
    timeout_s: float = 60.0,
    user_agent: Optional[str] = None,
    referer: Optional[str] = None,
    attempts: int = 3,
) -> tuple[str, bytes]:
    """Fetch ``url`` over plain HTTP, returning ``(suggested_filename, bytes)``.

    Cookie sharing:
        Pass either ``page`` (cookies copied from ``page.context``) or
        ``context`` directly. When both are absent, the request is
        anonymous, which is fine for venues with no consent gate.

    The result is shaped to match what ``SaveLocalPipeline.save`` accepts
    — call sites can pass it through unchanged.
    """
    ctx = context or (page.context if page else None)
    headers: dict[str, str] = {}
    if user_agent:
        headers["User-Agent"] = user_agent
    elif page is not None:
        # Reuse the page's UA so server-side fingerprints match what was
        # observed during the consent flow.
        try:
            headers["User-Agent"] = await page.evaluate("() => navigator.userAgent")
        except Exception:
            pass
    if referer:
        headers["Referer"] = referer
    elif page is not None:
        headers["Referer"] = page.url
    headers.setdefault("Accept", "*/*")

    if ctx is not None:
        jar: aiohttp.CookieJar | None = await _cookie_jar_from_context(ctx, url)
    else:
        jar = None

    timeout = aiohttp.ClientTimeout(total=timeout_s)

    async def _do() -> tuple[str, bytes]:
        async with aiohttp.ClientSession(
            timeout=timeout, headers=headers, cookie_jar=jar,
        ) as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                # Prefer a Content-Disposition filename if the server
                # provided one, else fall back to URL-derived name.
                cd = resp.headers.get("Content-Disposition", "")
                filename: str
                if "filename=" in cd:
                    filename = cd.split("filename=", 1)[1].strip().strip('"')
                else:
                    filename = _filename_from_url(url)
                payload = await resp.read()
                logger.info(
                    "HTTP downloaded %d bytes from %s as %s",
                    len(payload), url, filename,
                )
                return filename, payload

    return await with_retry(
        _do, attempts=attempts, base_delay=2.0, max_delay=15.0,
        retry_on=(aiohttp.ClientError, asyncio.TimeoutError),
        label=f"http_download[{url}]",
    )


async def collect_anchor_urls(
    page: Page,
    selector: str,
    *,
    base_url: Optional[str] = None,
) -> list[tuple[str, str]]:
    """Return ``[(label, absolute_url), …]`` for every anchor matching ``selector``.

    Used by the HTTP fast path: the scraper navigates with Playwright
    (handles cookies), reads the anchor list with Playwright, and then
    streams each file via :func:`http_download`. No clicks involved.
    """
    base = base_url or page.url
    out: list[tuple[str, str]] = []
    anchors = await page.locator(selector).all()
    for a in anchors:
        href = await a.get_attribute("href")
        if not href:
            continue
        text = (await a.text_content()) or ""
        out.append((text.strip(), _absolute_url(href, base)))
    return out


__all__ = ["collect_anchor_urls", "http_download"]
