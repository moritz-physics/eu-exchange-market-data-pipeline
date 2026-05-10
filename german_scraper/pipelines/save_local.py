"""Local-disk bronze pipeline backed by the SQLite manifest.

Saves raw payloads under ``downloads/<subdir>/<filename>`` and records
each one in the manifest with its SHA-256 hash. Two layers of dedupe:

  * **Label dedupe** (the historical behaviour): cheap, used by scrapers
    *before* clicking a download link to avoid hitting the venue at all.
  * **Hash dedupe** (new): catches identical bytes re-released under a
    different filename, and lets the ingest job process each unique
    payload exactly once.
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from typing import Tuple, Union

from playwright.async_api import Download

from german_scraper.core.logging_config import get_logger
from german_scraper.core.manifest_db import (
    BronzeRecord,
    BronzeStatus,
    DEFAULT_MANIFEST_PATH,
    Manifest,
)

logger = get_logger(__name__)

DownloadInput = Union[Download, Tuple[str, bytes]]


class SaveLocalPipeline:
    """Bronze sink: persist raw bytes, hash them, register in the manifest."""

    ROOT: Path = Path("downloads")

    def __init__(
        self,
        root: Path | None = None,
        manifest: Manifest | None = None,
        manifest_path: Path | None = None,
    ) -> None:
        self.root = Path(root) if root else self.ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest = manifest or Manifest(manifest_path or DEFAULT_MANIFEST_PATH)
        self._lock = asyncio.Lock()

    # ── Legacy compatibility for callers that still pass labels ─────────
    def has_seen(self, label: str, *, exchange: str = "_any") -> bool:
        """True if any prior run recorded ``label`` for this exchange."""
        if exchange == "_any":
            # back-compat for older scrapers that didn't pass exchange
            return self._has_label_any_exchange(label)
        return self.manifest.has_bronze_label(exchange, label)

    def _has_label_any_exchange(self, label: str) -> bool:
        with self.manifest._conn() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                "SELECT 1 FROM bronze WHERE label=? LIMIT 1", (label,),
            ).fetchone()
        return row is not None

    def mark_seen(self, label: str, *, exchange: str = "_legacy") -> None:
        """Mark ``label`` as seen without an actual file (legacy API)."""
        sha = f"label-only:{exchange}:{label}"
        if self.manifest.has_bronze_sha(sha):
            return
        self.manifest.record_bronze(
            BronzeRecord(
                exchange=exchange,
                label=label,
                source_uri=f"label-only://{exchange}/{label}",
                bytes_size=0,
                sha256=sha,
                scraped_at=time.time(),
                status=BronzeStatus.INGESTED.value,
            )
        )

    remember = mark_seen  # alias used by Bratislava

    # ── Save API ────────────────────────────────────────────────────────
    async def save(
        self,
        download: DownloadInput,
        subdir: str,
        *,
        exchange: str | None = None,
        data_type: str | None = None,
    ) -> Path | None:
        """Persist a download, hash it, register it. Returns target path or None."""
        async with self._lock:
            sub = self.root / subdir
            sub.mkdir(parents=True, exist_ok=True)
            # Derive exchange from subdir if not provided so old scrapers Just Work.
            exchange = exchange or subdir.split("/", 1)[0]

            if isinstance(download, tuple):
                filename, data = download
                if self.manifest.has_bronze_label(exchange, filename):
                    logger.info("Already downloaded, skipping: %s", filename)
                    return None
                target = sub / filename
                target.write_bytes(data)
                sha = hashlib.sha256(data).hexdigest()
                self._record(target, filename, sha, len(data), exchange, data_type)
                logger.info("Saved → %s (%d bytes)", target, len(data))
                return target

            filename = download.suggested_filename
            if self.manifest.has_bronze_label(exchange, filename):
                logger.info("Already downloaded, skipping: %s", filename)
                return None
            target = sub / filename
            await download.save_as(target)
            data = target.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            self._record(target, filename, sha, len(data), exchange, data_type)
            logger.info("Saved → %s (%d bytes)", target, len(data))
            return target

    def _record(
        self,
        path: Path,
        label: str,
        sha: str,
        size: int,
        exchange: str,
        data_type: str | None,
    ) -> None:
        self.manifest.record_bronze(
            BronzeRecord(
                exchange=exchange,
                label=label,
                source_uri=str(path.resolve()),
                bytes_size=size,
                sha256=sha,
                scraped_at=time.time(),
                data_type=data_type,
            )
        )
