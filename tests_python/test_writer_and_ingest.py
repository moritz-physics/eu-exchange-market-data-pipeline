"""Writer round-trip and ingest pipeline tests."""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

from german_scraper.core.manifest_db import BronzeRecord, Manifest
from german_scraper.storage.backends import LocalBackend
from german_scraper.storage.parquet_writer import ParquetWriter
from german_scraper.storage.schema import (
    DataType, QuoteRecord, TradeFlag, TradeRecord,
)
from german_scraper.storage.ingest import run_ingest


def test_writer_roundtrip_single_partition(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path)
    writer = ParquetWriter(backend=backend, dry_run=False, manifest=None)
    ts = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
    records = [
        TradeRecord(
            event_ts=ts, exchange="X", data_type=DataType.POST_TRADE.value,
            isin="DE0001", instrument_type="equity",
            trade_price=10.0, trade_size=1.0,
        ),
        TradeRecord(
            event_ts=ts.replace(minute=1), exchange="X",
            data_type=DataType.POST_TRADE.value,
            isin="DE0001", instrument_type="equity",
            trade_price=10.5, trade_size=2.0,
        ),
    ]
    uris = writer.write(records)
    assert len(uris) == 1
    table = pq.ParquetFile(uris[0]).read()
    assert table.num_rows == 2
    # Sort assertion: event_ts ASC.
    times = table.column("event_ts").to_pylist()
    assert times == sorted(times)


def test_writer_routes_records_to_correct_tables(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path)
    writer = ParquetWriter(backend=backend, dry_run=False, manifest=None)
    ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
    records = [
        TradeRecord(event_ts=ts, exchange="X", data_type=DataType.POST_TRADE.value,
                    instrument_type="equity"),
        QuoteRecord(event_ts=ts, exchange="X", data_type=DataType.PRE_TRADE.value,
                    instrument_type="equity"),
    ]
    uris = writer.write(records)
    assert len(uris) == 2
    tables = sorted(uri.split("/data/")[-1].split("/")[0] for uri in uris)
    assert tables == ["quotes", "trades"]


def test_dry_run_writes_nothing(tmp_path: Path, capsys) -> None:
    backend = LocalBackend(tmp_path)
    writer = ParquetWriter(backend=backend, dry_run=True, manifest=None)
    ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
    record = TradeRecord(
        event_ts=ts, exchange="X", data_type=DataType.POST_TRADE.value,
    )
    writer.write([record])
    out = capsys.readouterr().out
    assert "DRY-RUN SIMULATION" in out
    # No files written
    assert list(tmp_path.rglob("*.parquet")) == []


def test_ingest_end_to_end(tmp_path: Path, tmp_manifest: Manifest) -> None:
    """Synthetic CSV → bronze → ingest → silver, no live network."""
    bronze_path = tmp_path / "downloads" / "berlin" / "posttrade"
    bronze_path.mkdir(parents=True)
    csv = (
        b"TradingDateTime,ISIN,Price,Quantity,Currency,Flags\n"
        b"2025-08-01T09:00:00Z,DE0007164600,42.78,125,EUR,LRGS\n"
        b"2025-08-01T09:01:00Z,DE0007164600,42.81,80,EUR,\n"
    )
    file = bronze_path / "test.csv"
    file.write_bytes(csv)

    sha = hashlib.sha256(csv).hexdigest()
    tmp_manifest.record_bronze(BronzeRecord(
        exchange="berlin/posttrade", label="test.csv",
        source_uri=str(file.resolve()), bytes_size=len(csv),
        sha256=sha, scraped_at=time.time(), data_type="post_trade",
    ))

    backend = LocalBackend(tmp_path)
    writer = ParquetWriter(backend=backend, dry_run=False, manifest=tmp_manifest)
    stats = run_ingest(manifest=tmp_manifest, writer=writer)
    assert stats.files_ok == 1
    assert stats.files_failed == 0
    assert stats.parsed_rows == 2

    parquet_files = list((tmp_path / "data").rglob("*.parquet"))
    assert len(parquet_files) == 1
    table = pq.ParquetFile(parquet_files[0]).read()
    assert table.num_rows == 2
    flags = sorted(set(table.column("trade_flag_canonical").to_pylist()))
    assert flags == [TradeFlag.LARGE_IN_SCALE.value, TradeFlag.NORMAL.value]


def test_ingest_dlq_on_writer_failure(
    tmp_path: Path, tmp_manifest: Manifest, monkeypatch,
) -> None:
    """A writer crash should land all bronze rows in FAILED, not lose them."""
    bronze_path = tmp_path / "downloads" / "berlin" / "posttrade"
    bronze_path.mkdir(parents=True)
    csv = (
        b"TradingDateTime,ISIN,Price,Quantity,Currency,Flags\n"
        b"2025-08-01T09:00:00Z,DE0007164600,42.78,125,EUR,\n"
    )
    file = bronze_path / "test.csv"
    file.write_bytes(csv)
    tmp_manifest.record_bronze(BronzeRecord(
        exchange="berlin/posttrade", label="test.csv",
        source_uri=str(file.resolve()), bytes_size=len(csv),
        sha256=hashlib.sha256(csv).hexdigest(), scraped_at=time.time(),
    ))

    backend = LocalBackend(tmp_path)

    class _Writer(ParquetWriter):
        def write(self, records):
            raise RuntimeError("synthetic writer failure")

    writer = _Writer(backend=backend, dry_run=False, manifest=None)
    stats = run_ingest(manifest=tmp_manifest, writer=writer)
    assert stats.files_failed == 1
    assert stats.files_ok == 0
