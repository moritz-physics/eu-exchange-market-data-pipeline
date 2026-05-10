"""SQLite-backed file manifest used across scrape and ingest.

Replaces the flat ``manifest.json`` set with a queryable, concurrency-safe
table that doubles as a lightweight catalog. The same database stores:

  * **bronze**: every raw payload acquired from a venue (the immutable
    source of truth).
  * **silver**: every parquet partition produced from bronze.

A single SQLite file (default ``manifest.db``) is sufficient up to
millions of rows; concurrency is handled by SQLite's WAL mode plus a
per-process ``threading.Lock`` to serialise writes. For multi-host
production, point ``MANIFEST_DSN`` at a real Postgres instance — the
code only uses ANSI SQL.

Why SQLite over JSON
====================

The previous JSON manifest was already 546 entries; loading and
rewriting on every download is O(n²) and not safe across processes. A
SQLite table answers operational questions for free: "how many BERA
files did we scrape last week", "what's still PENDING ingestion",
"which payloads failed the parser" — single-line ``sqlite3`` queries.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterator, Optional

from german_scraper.core.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_MANIFEST_PATH: Path = Path("manifest.db")


class BronzeStatus(str, Enum):
    """Lifecycle of a raw payload (bronze layer)."""

    DOWNLOADED = "downloaded"   # file persisted, not yet ingested
    INGESTED = "ingested"       # successfully parsed into silver
    FAILED = "failed"            # parser failed; sits in DLQ


class SilverStatus(str, Enum):
    """Lifecycle of a parquet partition (silver layer)."""

    WRITTEN = "written"
    COMPACTED = "compacted"     # rolled into a larger file
    EXPIRED = "expired"         # retention-policy deleted


@dataclass(frozen=True)
class BronzeRecord:
    """One raw payload landed by a scraper."""

    exchange: str
    label: str               # human-readable dedupe key (filename or link text)
    source_uri: str          # local path or s3:// URI
    bytes_size: int
    sha256: str
    scraped_at: float        # epoch seconds
    data_type: Optional[str] = None
    status: str = BronzeStatus.DOWNLOADED.value
    ingested_at: Optional[float] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class SilverRecord:
    """One Parquet partition file produced by ingest."""

    table: str               # quotes / trades / bars
    partition_path: str
    target_uri: str
    rows: int
    bytes_size: int
    written_at: float
    bronze_sha256: Optional[str] = None  # provenance back to bronze
    status: str = SilverStatus.WRITTEN.value


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bronze (
    sha256        TEXT PRIMARY KEY,
    exchange      TEXT NOT NULL,
    label         TEXT NOT NULL,
    source_uri    TEXT NOT NULL,
    bytes_size    INTEGER NOT NULL,
    scraped_at    REAL NOT NULL,
    data_type     TEXT,
    status        TEXT NOT NULL,
    ingested_at   REAL,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS bronze_exchange_label  ON bronze(exchange, label);
CREATE INDEX IF NOT EXISTS bronze_status          ON bronze(status);
CREATE INDEX IF NOT EXISTS bronze_scraped_at      ON bronze(scraped_at);

CREATE TABLE IF NOT EXISTS silver (
    target_uri      TEXT PRIMARY KEY,
    "table"         TEXT NOT NULL,
    partition_path  TEXT NOT NULL,
    rows            INTEGER NOT NULL,
    bytes_size      INTEGER NOT NULL,
    written_at      REAL NOT NULL,
    bronze_sha256   TEXT,
    status          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS silver_table_status ON silver("table", status);
CREATE INDEX IF NOT EXISTS silver_written_at   ON silver(written_at);

CREATE TABLE IF NOT EXISTS run_log (
    run_id      TEXT PRIMARY KEY,
    started_at  REAL NOT NULL,
    ended_at    REAL,
    exchange    TEXT,
    files_new   INTEGER DEFAULT 0,
    files_skip  INTEGER DEFAULT 0,
    rows_total  INTEGER DEFAULT 0,
    error       TEXT
);
"""


class Manifest:
    """SQLite-backed manifest. Thread- and process-safe via WAL + lock."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else Path(
            os.environ.get("MANIFEST_DSN", str(DEFAULT_MANIFEST_PATH))
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        """Yield a per-call connection; cheap because SQLite stays open."""
        conn = sqlite3.connect(
            self.path, timeout=30, isolation_level=None,  # autocommit; we use explicit txns
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript(_SCHEMA_SQL)

    # ── Bronze API ───────────────────────────────────────────────────────
    def has_bronze_label(self, exchange: str, label: str) -> bool:
        """Filename-style dedupe used by scrapers before downloading."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM bronze WHERE exchange=? AND label=? LIMIT 1",
                (exchange, label),
            ).fetchone()
        return row is not None

    def has_bronze_sha(self, sha256: str) -> bool:
        """Hash-based dedupe used post-download to catch re-released files."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM bronze WHERE sha256=? LIMIT 1", (sha256,)
            ).fetchone()
        return row is not None

    def record_bronze(self, rec: BronzeRecord) -> None:
        """Insert a fresh bronze entry. Idempotent on (sha256)."""
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO bronze
                   (sha256, exchange, label, source_uri, bytes_size,
                    scraped_at, data_type, status, ingested_at, error)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    rec.sha256, rec.exchange, rec.label, rec.source_uri,
                    rec.bytes_size, rec.scraped_at, rec.data_type,
                    rec.status, rec.ingested_at, rec.error,
                ),
            )

    def list_pending_bronze(
        self, exchange: Optional[str] = None, limit: int = 1000,
    ) -> list[BronzeRecord]:
        """All bronze rows that haven't been ingested yet (oldest first)."""
        sql = "SELECT * FROM bronze WHERE status=? "
        args: list = [BronzeStatus.DOWNLOADED.value]
        if exchange:
            sql += "AND exchange=? "
            args.append(exchange)
        sql += "ORDER BY scraped_at ASC LIMIT ?"
        args.append(limit)
        with self._conn() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._row_to_bronze(r) for r in rows]

    def mark_bronze_ingested(self, sha256: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE bronze SET status=?, ingested_at=?, error=NULL "
                "WHERE sha256=?",
                (BronzeStatus.INGESTED.value, time.time(), sha256),
            )

    def mark_bronze_failed(self, sha256: str, error: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE bronze SET status=?, error=? WHERE sha256=?",
                (BronzeStatus.FAILED.value, error[:1024], sha256),
            )

    # ── Silver API ───────────────────────────────────────────────────────
    def record_silver(self, rec: SilverRecord) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO silver
                   (target_uri, "table", partition_path, rows, bytes_size,
                    written_at, bronze_sha256, status)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    rec.target_uri, rec.table, rec.partition_path,
                    rec.rows, rec.bytes_size, rec.written_at,
                    rec.bronze_sha256, rec.status,
                ),
            )

    # ── Stats / observability ────────────────────────────────────────────
    def stats(self) -> dict[str, dict[str, int]]:
        """Counts by table+status; cheap and useful from the CLI."""
        out: dict[str, dict[str, int]] = {"bronze": {}, "silver": {}}
        with self._conn() as conn:
            for row in conn.execute(
                "SELECT status, COUNT(*) AS n FROM bronze GROUP BY status"
            ):
                out["bronze"][row["status"]] = row["n"]
            for row in conn.execute(
                "SELECT status, COUNT(*) AS n FROM silver GROUP BY status"
            ):
                out["silver"][row["status"]] = row["n"]
        return out

    @staticmethod
    def _row_to_bronze(row: sqlite3.Row) -> BronzeRecord:
        return BronzeRecord(
            sha256=row["sha256"],
            exchange=row["exchange"],
            label=row["label"],
            source_uri=row["source_uri"],
            bytes_size=row["bytes_size"],
            scraped_at=row["scraped_at"],
            data_type=row["data_type"],
            status=row["status"],
            ingested_at=row["ingested_at"],
            error=row["error"],
        )


# ── One-time migration helper ────────────────────────────────────────────
def import_legacy_json_manifest(
    legacy_path: Path | str, manifest: Manifest, *, exchange: str = "legacy",
) -> int:
    """Backfill the new SQLite manifest from the old ``manifest.json``.

    Each entry is recorded with a synthetic sha256 (``legacy:{label}``) so
    ``has_bronze_label`` continues to skip already-downloaded files. Returns
    the number of rows imported.
    """
    import json
    legacy = Path(legacy_path)
    if not legacy.exists():
        return 0
    with legacy.open("r", encoding="utf-8") as f:
        labels = json.load(f)
    n = 0
    for label in labels:
        rec = BronzeRecord(
            exchange=exchange,
            label=label,
            source_uri=f"legacy://{label}",
            bytes_size=0,
            sha256=f"legacy:{label}",
            scraped_at=time.time(),
            status=BronzeStatus.INGESTED.value,
        )
        manifest.record_bronze(rec)
        n += 1
    logger.info("Imported %d legacy manifest entries from %s", n, legacy)
    return n


__all__ = [
    "BronzeRecord",
    "BronzeStatus",
    "DEFAULT_MANIFEST_PATH",
    "Manifest",
    "SilverRecord",
    "SilverStatus",
    "import_legacy_json_manifest",
]
