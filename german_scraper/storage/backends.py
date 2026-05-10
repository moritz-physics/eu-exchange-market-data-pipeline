"""Pluggable storage backends for Parquet partition output.

The same write interface is available for local disk (development),
S3-compatible object storage (production cloud deploys), and POSIX network
file systems (NFS, GPFS, Lustre — common in research-cluster setups).

In ``DRY_RUN`` mode no backend method is invoked: the writer prints a
simulation report instead.
"""
from __future__ import annotations

import io
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from german_scraper.core.logging_config import get_logger

logger = get_logger(__name__)


class StorageBackend(ABC):
    """Minimal write interface implemented by all backends."""

    name: str = "abstract"

    @abstractmethod
    def write_bytes(self, key: str, payload: bytes) -> str:
        """Persist ``payload`` under ``key`` and return a stable URI."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return whether ``key`` already has a payload at this backend."""


class LocalBackend(StorageBackend):
    """POSIX-local backend rooted at a configurable directory."""

    name: str = "local"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / key

    def write_bytes(self, key: str, payload: bytes) -> str:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(payload)
        tmp.replace(target)
        logger.info("LocalBackend wrote %d bytes to %s", len(payload), target)
        return str(target.resolve())

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


class NFSBackend(LocalBackend):
    """Network-file-system backend.

    Functionally identical to :class:`LocalBackend` because NFS / GPFS /
    Lustre present a POSIX surface, but kept as a separate class so the
    deployment intent is explicit in logs and configuration.
    """

    name: str = "nfs"


class S3Backend(StorageBackend):
    """S3-compatible object-storage backend.

    Defers boto3 import until first use so the rest of the code base does
    not depend on it. ``AWS_*`` credentials are read by boto3 in the usual
    way (env, instance profile, ``~/.aws/credentials``).
    """

    name: str = "s3"

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        endpoint_url: Optional[str] = None,
        region_name: Optional[str] = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.endpoint_url = endpoint_url
        self.region_name = region_name
        self._client = None  # lazy

    def _get_client(self):
        if self._client is None:
            try:
                import boto3  # type: ignore
            except ImportError as exc:
                raise RuntimeError(
                    "S3Backend requires the 'boto3' package; install it or "
                    "switch STORAGE_BACKEND to 'local' / 'nfs'."
                ) from exc
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                region_name=self.region_name,
            )
        return self._client

    def _full_key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def write_bytes(self, key: str, payload: bytes) -> str:
        full_key = self._full_key(key)
        self._get_client().upload_fileobj(io.BytesIO(payload), self.bucket, full_key)
        uri = f"s3://{self.bucket}/{full_key}"
        logger.info("S3Backend wrote %d bytes to %s", len(payload), uri)
        return uri

    def exists(self, key: str) -> bool:
        full_key = self._full_key(key)
        try:
            self._get_client().head_object(Bucket=self.bucket, Key=full_key)
            return True
        except Exception:
            return False
