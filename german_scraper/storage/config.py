"""Environment-driven configuration for the storage layer.

Single place where the deployment target is resolved. On a developer
laptop this defaults to a local backend rooted at ``./data`` with
``DRY_RUN=True``; on a server it is overridden via env vars without any
code change.

Recognised environment variables
================================

DRY_RUN              : "true" | "false"  (default: "true")
STORAGE_BACKEND      : "local" | "nfs" | "s3"  (default: "local")
STORAGE_LOCAL_ROOT   : path for local / nfs backends (default: "./data")
STORAGE_S3_BUCKET    : bucket for s3 backend
STORAGE_S3_PREFIX    : key prefix for s3 backend (default: "")
STORAGE_S3_ENDPOINT  : optional non-AWS endpoint (e.g. MinIO)
STORAGE_S3_REGION    : optional region override

PARQUET_COMPRESSION  : "snappy" | "zstd" | "gzip" (default: "snappy")
PARQUET_ROW_GROUP    : int rows per row group (default: 65536)
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from german_scraper.core.logging_config import get_logger
from german_scraper.storage.backends import (
    LocalBackend,
    NFSBackend,
    S3Backend,
    StorageBackend,
)

logger = get_logger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Module-level flag so callers can `from german_scraper.storage import DRY_RUN`
# and reason about the active mode without re-resolving env each time.
DRY_RUN: bool = _env_bool("DRY_RUN", True)


@dataclass
class StorageConfig:
    """Resolved storage configuration derived from environment variables."""

    backend: StorageBackend
    compression: str = "snappy"
    row_group_size: int = 64 * 1024
    dry_run: bool = DRY_RUN

    @classmethod
    def from_env(cls) -> "StorageConfig":
        """Build a :class:`StorageConfig` from current env vars."""
        kind = os.environ.get("STORAGE_BACKEND", "local").lower()
        if kind == "local":
            backend: StorageBackend = LocalBackend(
                os.environ.get("STORAGE_LOCAL_ROOT", ".")
            )
        elif kind == "nfs":
            backend = NFSBackend(
                os.environ.get("STORAGE_LOCAL_ROOT", ".")
            )
        elif kind == "s3":
            bucket = os.environ.get("STORAGE_S3_BUCKET")
            if not bucket:
                raise RuntimeError(
                    "STORAGE_BACKEND=s3 requires STORAGE_S3_BUCKET to be set."
                )
            backend = S3Backend(
                bucket=bucket,
                prefix=os.environ.get("STORAGE_S3_PREFIX", ""),
                endpoint_url=os.environ.get("STORAGE_S3_ENDPOINT"),
                region_name=os.environ.get("STORAGE_S3_REGION"),
            )
        else:
            raise RuntimeError(f"Unknown STORAGE_BACKEND={kind!r}")

        compression = os.environ.get("PARQUET_COMPRESSION", "snappy").lower()
        row_group = int(os.environ.get("PARQUET_ROW_GROUP", str(64 * 1024)))

        cfg = cls(
            backend=backend,
            compression=compression,
            row_group_size=row_group,
            dry_run=DRY_RUN,
        )
        logger.info(
            "StorageConfig backend=%s compression=%s dry_run=%s",
            backend.name, compression, DRY_RUN,
        )
        return cfg


def get_default_writer():
    """Return a :class:`ParquetWriter` configured from environment variables."""
    from german_scraper.storage.parquet_writer import ParquetWriter
    cfg = StorageConfig.from_env()
    return ParquetWriter(
        backend=cfg.backend,
        compression=cfg.compression,
        row_group_size=cfg.row_group_size,
        dry_run=cfg.dry_run,
    )


__all__ = ["DRY_RUN", "StorageConfig", "get_default_writer"]
