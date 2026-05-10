"""Reproducible end-to-end dry-run of the storage layer.

Run with:
    DRY_RUN=true uv run python -m german_scraper.storage.dry_run_demo

This produces synthetic records covering the four canonical record shapes
this pipeline emits in production — pre-trade quote, post-trade trade,
order-book snapshot, OHLCV bar — and feeds them through
:class:`ParquetWriter`. The simulation report shown is exactly what a
real ingestion pass would print.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from german_scraper.core.logging_config import configure_logging
from german_scraper.storage import (
    DataType,
    StorageConfig,
    UnifiedRecord,
)
from german_scraper.storage.parquet_writer import ParquetWriter


def _build_sample_records() -> list[UnifiedRecord]:
    """A handful of records spanning every shape the schema supports."""
    base = datetime(2025, 8, 1, 9, 30, 0, tzinfo=timezone.utc)
    return [
        # post-trade equity execution (Boerse Berlin / RTS-13 style)
        UnifiedRecord(
            event_ts=base,
            exchange="BERA",
            mic="BERA",
            data_type=DataType.POST_TRADE.value,
            instrument_type="equity",
            instrument_id="DE0007164600",
            instrument_id_type="ISIN",
            currency="EUR",
            trade_price=42.78,
            trade_size=125.0,
            trade_id="BERA-20250801-0001",
            notional=42.78 * 125.0,
            trade_flags="LRGS",
            source_file="Mifir13DelayedDataPT_BERA_00000007_20250801.csv",
        ),
        UnifiedRecord(
            event_ts=base.replace(hour=9, minute=31),
            exchange="BERA",
            mic="BERA",
            data_type=DataType.POST_TRADE.value,
            instrument_type="equity",
            instrument_id="DE0007164600",
            instrument_id_type="ISIN",
            currency="EUR",
            trade_price=42.81,
            trade_size=80.0,
            trade_id="BERA-20250801-0002",
            notional=42.81 * 80.0,
            source_file="Mifir13DelayedDataPT_BERA_00000007_20250801.csv",
        ),

        # pre-trade quote (Cboe Europe BXE)
        UnifiedRecord(
            event_ts=base,
            exchange="CBOE-BXE",
            mic="BATE",
            data_type=DataType.PRE_TRADE.value,
            instrument_type="equity",
            instrument_id="GB00B16GWD56",
            instrument_id_type="ISIN",
            currency="GBP",
            bid_price=12.345,
            bid_size=500.0,
            ask_price=12.350,
            ask_size=400.0,
            book_level=1,
            source_file="rts13_public_trade_data_bxe_2025-08-01_09.csv",
        ),

        # bond OHLCV bar (Bank of Greece HDAT)
        UnifiedRecord(
            event_ts=base,
            exchange="BOG-HDAT",
            mic="HDAT",
            data_type=DataType.POST_TRADE.value,
            instrument_type="bond",
            instrument_id="GR0114030555",
            instrument_id_type="ISIN",
            currency="EUR",
            open=99.85,
            high=100.05,
            low=99.80,
            close=99.95,
            volume=2_500_000.0,
            source_file="PostTradeHDAT.json",
        ),

        # energy futures execution (ICE)
        UnifiedRecord(
            event_ts=base,
            exchange="ICE",
            mic="IFEU",
            data_type=DataType.POST_TRADE.value,
            instrument_type="energy",
            instrument_id="BRN-Z25",
            instrument_id_type="INTERNAL",
            currency="USD",
            trade_price=82.34,
            trade_size=10.0,
            trade_id="ICE-BRN-Z25-001",
            notional=823_400.0,
            source_file="ice_post_brn_z25.csv",
        ),
    ]


def main() -> None:
    """Build sample records, write them via ParquetWriter, print the report."""
    configure_logging()
    os.environ.setdefault("DRY_RUN", "true")

    cfg = StorageConfig.from_env()
    writer = ParquetWriter(
        backend=cfg.backend,
        compression=cfg.compression,
        row_group_size=cfg.row_group_size,
        dry_run=True,
    )
    writer.write(_build_sample_records())


if __name__ == "__main__":
    main()
