"""Schema-stability + record-construction tests.

These pin the silver schema. Any change to ``UNIFIED_SCHEMA`` /
``TRADES_SCHEMA`` / ``QUOTES_SCHEMA`` / ``BARS_SCHEMA`` must bump
``SCHEMA_VERSION`` — the test enforces that link.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pyarrow as pa

from german_scraper.storage.schema import (
    BARS_SCHEMA,
    BarRecord,
    DataType,
    QUOTES_SCHEMA,
    QuoteRecord,
    SCHEMA_VERSION,
    SCHEMAS,
    TRADES_SCHEMA,
    TradeFlag,
    TradeRecord,
    records_to_table,
)


# Snapshot the schemas; if you change this list you must also bump SCHEMA_VERSION.
EXPECTED_TRADES_FIELDS = {
    "event_ts", "publication_ts", "received_ts", "ingest_ts", "seq",
    "exchange", "mic", "data_type",
    "isin", "ticker", "figi", "venue_instrument_id",
    "instrument_type", "currency", "venue_segment",
    "source_file", "source_url", "source_msg_hash", "schema_version",
    "trade_price", "trade_size", "trade_id", "notional",
    "side", "trade_flag_canonical", "trade_flags_raw",
}

EXPECTED_QUOTES_FIELDS = {
    "event_ts", "publication_ts", "received_ts", "ingest_ts", "seq",
    "exchange", "mic", "data_type",
    "isin", "ticker", "figi", "venue_instrument_id",
    "instrument_type", "currency", "venue_segment",
    "source_file", "source_url", "source_msg_hash", "schema_version",
    "bid_price", "bid_size", "ask_price", "ask_size", "book_level", "snapshot",
}

EXPECTED_BARS_FIELDS = {
    "event_ts", "publication_ts", "received_ts", "ingest_ts", "seq",
    "exchange", "mic", "data_type",
    "isin", "ticker", "figi", "venue_instrument_id",
    "instrument_type", "currency", "venue_segment",
    "source_file", "source_url", "source_msg_hash", "schema_version",
    "bar_interval", "open", "high", "low", "close", "volume",
    "vwap", "trades_count",
}


def test_schema_version_is_pinned() -> None:
    assert SCHEMA_VERSION == "2.0.0", (
        "SCHEMA_VERSION change requires a corresponding update to "
        "this test and downstream consumers"
    )


def test_trades_schema_fields_are_stable() -> None:
    actual = {f.name for f in TRADES_SCHEMA}
    assert actual == EXPECTED_TRADES_FIELDS, (
        f"TRADES_SCHEMA changed: added={actual - EXPECTED_TRADES_FIELDS}, "
        f"removed={EXPECTED_TRADES_FIELDS - actual} — bump SCHEMA_VERSION"
    )


def test_quotes_schema_fields_are_stable() -> None:
    actual = {f.name for f in QUOTES_SCHEMA}
    assert actual == EXPECTED_QUOTES_FIELDS


def test_bars_schema_fields_are_stable() -> None:
    actual = {f.name for f in BARS_SCHEMA}
    assert actual == EXPECTED_BARS_FIELDS


def test_required_fields_validation() -> None:
    rec = TradeRecord(
        # event_ts missing on purpose
        exchange="X", data_type=DataType.POST_TRADE.value,
    )
    with pytest.raises(ValueError, match="event_ts"):
        records_to_table([rec])


def test_invalid_data_type_rejected() -> None:
    rec = TradeRecord(
        event_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
        exchange="X", data_type="bogus",
    )
    with pytest.raises(ValueError, match="data_type"):
        records_to_table([rec])


def test_invalid_canonical_flag_rejected() -> None:
    rec = TradeRecord(
        event_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
        exchange="X", data_type=DataType.POST_TRADE.value,
        trade_flag_canonical="not_a_real_flag",
    )
    with pytest.raises(ValueError, match="trade_flag_canonical"):
        records_to_table([rec])


def test_records_to_table_routes_by_TABLE() -> None:
    ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
    trade = TradeRecord(
        event_ts=ts, exchange="X", data_type=DataType.POST_TRADE.value,
        trade_price=1.0, trade_size=2.0,
    )
    quote = QuoteRecord(
        event_ts=ts, exchange="X", data_type=DataType.PRE_TRADE.value,
        bid_price=1.0, ask_price=1.1,
    )
    bar = BarRecord(
        event_ts=ts, exchange="X", data_type=DataType.POST_TRADE.value,
        open=1.0, close=1.0,
    )

    name, table = records_to_table([trade])
    assert name == "trades"
    assert table.schema.equals(TRADES_SCHEMA)

    name, table = records_to_table([quote])
    assert name == "quotes"

    name, table = records_to_table([bar])
    assert name == "bars"

    # Mixed batches should fail.
    with pytest.raises(ValueError, match="same TABLE"):
        records_to_table([trade, quote])  # type: ignore[list-item]


def test_data_type_enum_values_match_schema() -> None:
    assert set(DataType.values()) == {"pre_trade", "post_trade"}
    assert set(SCHEMAS) == {"trades", "quotes", "bars"}
