"""End-to-end dry-run of the silver storage layer.

Run with:
    DRY_RUN=true uv run python -m german_scraper.storage.dry_run_demo

Builds a representative mix of trade, quote, and bar records — touching
every column the silver schemas define — and runs them through
:class:`ParquetWriter`. Output mirrors what an ingest pass on real
bronze data would produce.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from german_scraper.core.logging_config import configure_logging
from german_scraper.storage import (
    BarRecord,
    DataType,
    QuoteRecord,
    StorageConfig,
    TradeFlag,
    TradeRecord,
)
from german_scraper.storage.parquet_writer import ParquetWriter


def _build_sample_records() -> list:
    base = datetime(2025, 8, 1, 9, 30, 0, tzinfo=timezone.utc)
    received = datetime(2025, 8, 1, 9, 45, 0, tzinfo=timezone.utc)  # 15-min delay

    trades = [
        TradeRecord(
            event_ts=base,
            publication_ts=received,
            received_ts=received,
            seq=1,
            exchange="BERA",
            mic="BERA",
            data_type=DataType.POST_TRADE.value,
            isin="DE0007164600",
            ticker="SAP",
            instrument_type="equity",
            currency="EUR",
            trade_price=42.78,
            trade_size=125.0,
            trade_id="BERA-20250801-0001",
            notional=42.78 * 125.0,
            side="buy",
            trade_flags_raw="LRGS",
            trade_flag_canonical=TradeFlag.LARGE_IN_SCALE.value,
            source_file="Mifir13DelayedDataPT_BERA_00000007_20250801.csv",
            source_msg_hash="hash-bera-1",
        ),
        TradeRecord(
            event_ts=base.replace(minute=31),
            received_ts=received,
            seq=2,
            exchange="BERA",
            mic="BERA",
            data_type=DataType.POST_TRADE.value,
            isin="DE0007164600",
            ticker="SAP",
            instrument_type="equity",
            currency="EUR",
            trade_price=42.81,
            trade_size=80.0,
            trade_id="BERA-20250801-0002",
            notional=42.81 * 80.0,
            trade_flag_canonical=TradeFlag.NORMAL.value,
            source_file="Mifir13DelayedDataPT_BERA_00000007_20250801.csv",
            source_msg_hash="hash-bera-2",
        ),
        TradeRecord(
            event_ts=base,
            received_ts=received,
            seq=1,
            exchange="ICE",
            mic="IFEU",
            data_type=DataType.POST_TRADE.value,
            venue_instrument_id="BRN-Z25",
            instrument_type="energy",
            currency="USD",
            trade_price=82.34,
            trade_size=10.0,
            trade_id="ICE-BRN-Z25-001",
            notional=823_400.0,
            trade_flag_canonical=TradeFlag.NORMAL.value,
            source_file="ice_post_brn_z25.csv",
            source_msg_hash="hash-ice-1",
        ),
    ]

    quotes = [
        QuoteRecord(
            event_ts=base,
            received_ts=received,
            seq=1,
            exchange="CBOE-BXE",
            mic="BATE",
            data_type=DataType.PRE_TRADE.value,
            isin="GB00B16GWD56",
            ticker="VOD",
            instrument_type="equity",
            currency="GBP",
            bid_price=12.345,
            bid_size=500.0,
            ask_price=12.350,
            ask_size=400.0,
            book_level=1,
            snapshot=True,
            source_file="rts13_public_trade_data_bxe_2025-08-01_09.csv",
            source_msg_hash="hash-bxe-1",
        ),
    ]

    bars = [
        BarRecord(
            event_ts=base,
            received_ts=received,
            exchange="BOG-HDAT",
            mic="HDAT",
            data_type=DataType.POST_TRADE.value,
            isin="GR0114030555",
            instrument_type="bond",
            currency="EUR",
            bar_interval="1d",
            open=99.85,
            high=100.05,
            low=99.80,
            close=99.95,
            volume=2_500_000.0,
            vwap=99.94,
            trades_count=37,
            source_file="PostTradeHDAT.json",
            source_msg_hash="hash-bog-1",
        ),
    ]

    return trades + quotes + bars


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
