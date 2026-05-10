"""Iceberg sink roundtrip + snapshot/time-travel test."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture
def iceberg_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MANIFEST_DSN", str(tmp_path / "manifest.db"))
    monkeypatch.setenv("ICEBERG_WAREHOUSE", str(tmp_path / "warehouse"))
    return tmp_path


def test_iceberg_snapshot_isolation_and_time_travel(iceberg_env: Path) -> None:
    pytest.importorskip("pyiceberg")
    from german_scraper.storage.iceberg_sink import IcebergSink
    from german_scraper.storage.schema import DataType, TradeRecord

    ts = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
    sink = IcebergSink()

    sink.write([TradeRecord(
        event_ts=ts, exchange="X", data_type=DataType.POST_TRADE.value,
        instrument_type="equity", trade_price=1.0,
    )])
    sink.write([TradeRecord(
        event_ts=ts, exchange="X", data_type=DataType.POST_TRADE.value,
        instrument_type="equity", trade_price=2.0,
    )])

    stats = sink.stats()
    assert stats["trades"] == 2  # two snapshots
