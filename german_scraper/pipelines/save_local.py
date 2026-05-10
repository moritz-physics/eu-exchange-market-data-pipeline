"""Local-disk pipeline that saves Playwright downloads under ``downloads/``.

The pipeline tracks already-downloaded files in a manifest so re-running the
scraper never re-downloads the same payload twice. The manifest is keyed by
the human-readable label the scraper passes in, which is typically the
suggested filename or the link text.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Tuple, Union

from playwright.async_api import Download

from german_scraper.core.logging_config import get_logger

logger = get_logger(__name__)

DownloadInput = Union[Download, Tuple[str, bytes]]


class SaveLocalPipeline:
    """Persist downloads under ``downloads/<subdir>/<filename>``.

    The manifest is JSON-encoded for easy inspection. Concurrent writes are
    serialised through an asyncio lock so multiple scrapers can share one
    pipeline instance without corrupting the manifest.
    """

    ROOT: Path = Path("downloads")
    MANIFEST_PATH: Path = Path("german_scraper/core/manifest.json")

    def __init__(self, root: Path | None = None, manifest_path: Path | None = None) -> None:
        self.root = Path(root) if root else self.ROOT
        self.manifest_path = Path(manifest_path) if manifest_path else self.MANIFEST_PATH
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._load_manifest()

    def _load_manifest(self) -> None:
        if self.manifest_path.exists():
            try:
                with self.manifest_path.open("r", encoding="utf-8") as f:
                    self.seen: set[str] = set(json.load(f))
            except (OSError, json.JSONDecodeError) as exc:
                logger.error("Failed to read manifest %s: %s — starting fresh", self.manifest_path, exc)
                self.seen = set()
        else:
            self.seen = set()

    def _save_manifest(self) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.manifest_path.with_suffix(self.manifest_path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(sorted(self.seen), f, indent=2)
        tmp.replace(self.manifest_path)

    def has_seen(self, label: str) -> bool:
        """Return whether ``label`` has been downloaded in a prior run."""
        return label in self.seen

    def mark_seen(self, label: str) -> None:
        """Add ``label`` to the manifest and persist it to disk."""
        self.seen.add(label)
        self._save_manifest()

    # Alias for callers (Bratislava) that look for an arbitrary remember() hook
    remember = mark_seen

    async def save(self, download: DownloadInput, subdir: str) -> Path | None:
        """Persist a Playwright download or in-memory ``(name, bytes)`` pair.

        Returns the saved path or ``None`` if the file was already in the
        manifest.
        """
        async with self._lock:
            sub = self.root / subdir
            sub.mkdir(parents=True, exist_ok=True)

            if isinstance(download, tuple):
                filename, data = download
                target = sub / filename
                if self.has_seen(filename):
                    logger.info("Already downloaded, skipping: %s", filename)
                    return None
                target.write_bytes(data)
                logger.info("Saved → %s", target)
                self.mark_seen(filename)
                return target

            filename = download.suggested_filename
            if self.has_seen(filename):
                logger.info("Already downloaded, skipping: %s", filename)
                return None

            target = sub / filename
            await download.save_as(target)
            logger.info("Saved → %s", target)
            self.mark_seen(filename)
            return target
