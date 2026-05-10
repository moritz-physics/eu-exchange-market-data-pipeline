"""SQLite manifest contract tests."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from german_scraper.core.manifest_db import (
    BronzeRecord,
    BronzeStatus,
    Manifest,
    SilverRecord,
    SilverStatus,
    import_legacy_json_manifest,
)


def _bronze(**kw):
    base = dict(
        exchange="BERA", label="x.csv", source_uri="/tmp/x.csv",
        bytes_size=1, sha256="aaa", scraped_at=time.time(),
    )
    base.update(kw)
    return BronzeRecord(**base)


def test_bronze_insert_and_dedupe(tmp_manifest: Manifest) -> None:
    tmp_manifest.record_bronze(_bronze(sha256="h1"))
    tmp_manifest.record_bronze(_bronze(sha256="h1"))  # duplicate sha
    pending = tmp_manifest.list_pending_bronze()
    assert len(pending) == 1
    assert tmp_manifest.has_bronze_label("BERA", "x.csv")
    assert tmp_manifest.has_bronze_sha("h1")
    assert not tmp_manifest.has_bronze_sha("h2")


def test_bronze_lifecycle_transitions(tmp_manifest: Manifest) -> None:
    tmp_manifest.record_bronze(_bronze(sha256="h1"))
    assert tmp_manifest.list_pending_bronze() != []
    tmp_manifest.mark_bronze_ingested("h1")
    assert tmp_manifest.list_pending_bronze() == []
    assert tmp_manifest.stats()["bronze"][BronzeStatus.INGESTED.value] == 1


def test_failed_dlq_status(tmp_manifest: Manifest) -> None:
    tmp_manifest.record_bronze(_bronze(sha256="h1"))
    tmp_manifest.mark_bronze_failed("h1", "boom")
    assert tmp_manifest.stats()["bronze"][BronzeStatus.FAILED.value] == 1


def test_silver_insert(tmp_manifest: Manifest) -> None:
    tmp_manifest.record_silver(SilverRecord(
        table="trades", partition_path="exchange=X/year=2025",
        target_uri="file:///x.parquet", rows=10, bytes_size=1024,
        written_at=time.time(),
    ))
    assert tmp_manifest.stats()["silver"][SilverStatus.WRITTEN.value] == 1


def test_legacy_json_import(tmp_path: Path, tmp_manifest: Manifest) -> None:
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps(["a.csv", "b.csv", "c.csv"]))
    n = import_legacy_json_manifest(legacy, tmp_manifest, exchange="legacy")
    assert n == 3
    # Re-import is idempotent on sha
    n2 = import_legacy_json_manifest(legacy, tmp_manifest, exchange="legacy")
    assert n2 == 3
    # But the bronze table still has only 3 distinct entries.
    assert tmp_manifest.stats()["bronze"][BronzeStatus.INGESTED.value] == 3
