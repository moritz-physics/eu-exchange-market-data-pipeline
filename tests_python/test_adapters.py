"""Golden-input tests for the per-payload adapters."""
from __future__ import annotations

import json
from datetime import timezone

from german_scraper.storage.adapters import (
    adapt_bme_posttrade_json,
    adapt_bog_hdat_json,
    adapt_rts13_csv,
    canonical_trade_flag,
)
from german_scraper.storage.schema import DataType, TradeFlag


def test_canonical_trade_flag_known_codes() -> None:
    assert canonical_trade_flag("LRGS") == TradeFlag.LARGE_IN_SCALE.value
    assert canonical_trade_flag("BENC") == TradeFlag.BENCHMARK.value
    assert canonical_trade_flag("NPFT") == TradeFlag.NEGOTIATED.value
    assert canonical_trade_flag("CANC") == TradeFlag.CANCEL.value


def test_canonical_trade_flag_priority_with_combos() -> None:
    # LARGE_IN_SCALE > BENCHMARK
    assert canonical_trade_flag("BENC,LRGS") == TradeFlag.LARGE_IN_SCALE.value
    assert canonical_trade_flag("LRGS;BENC") == TradeFlag.LARGE_IN_SCALE.value


def test_canonical_trade_flag_falls_through() -> None:
    assert canonical_trade_flag(None) == TradeFlag.NORMAL.value
    assert canonical_trade_flag("") == TradeFlag.NORMAL.value
    assert canonical_trade_flag("ZZZZ") == TradeFlag.UNKNOWN.value


def test_adapt_rts13_csv_yields_typed_trade_records() -> None:
    payload = (
        b"TradingDateTime,ISIN,Price,Quantity,Currency,TradeID,Flags\n"
        b"2025-08-01T09:00:00Z,DE0007164600,42.78,125,EUR,T1,LRGS\n"
        b"2025-08-01T09:01:00Z,DE0007164600,42.81,80,EUR,T2,\n"
        b"NOT_A_TIMESTAMP,DE0007164600,42.81,80,EUR,T3,\n"  # filtered out
    )
    records = list(adapt_rts13_csv(
        payload, exchange="BERA", mic="BERA",
        data_type=DataType.POST_TRADE, source_file="test.csv",
    ))
    assert len(records) == 2  # bad timestamp filtered out
    r = records[0]
    assert r.event_ts.tzinfo == timezone.utc
    assert r.exchange == "BERA"
    assert r.isin == "DE0007164600"
    assert r.trade_price == 42.78
    assert r.trade_size == 125.0
    assert r.notional == 42.78 * 125.0
    assert r.trade_flag_canonical == TradeFlag.LARGE_IN_SCALE.value
    assert r.trade_flags_raw == "LRGS"
    assert r.source_msg_hash is not None
    assert r.seq == 1
    assert records[1].seq == 2


def test_adapt_bme_posttrade_json() -> None:
    doc = [
        {
            "trading_datetime": "2025-08-01T10:00:00",
            "isin": "ES0148396015",
            "price": "11.23",
            "volume": "500",
            "currency": "EUR",
            "flags": "BENC",
        },
        {
            "trading_datetime": "2025-08-01T10:01:00",
            "isin": "ES0148396015",
            "price": "11.25",
            "volume": "100",
            "currency": "EUR",
        },
    ]
    payload = json.dumps(doc).encode("utf-8")
    records = list(adapt_bme_posttrade_json(payload, source_file="bme.json"))
    assert len(records) == 2
    assert records[0].trade_flag_canonical == TradeFlag.BENCHMARK.value
    assert records[1].trade_flag_canonical == TradeFlag.NORMAL.value
    assert records[0].mic == "BMEX"
    assert records[0].notional == 11.23 * 500


def test_adapt_bog_hdat_json_yields_bar_records() -> None:
    doc = [{"date": "2025-08-01", "isin": "GR0114030555",
            "open": 99.85, "high": 100.05, "low": 99.80, "close": 99.95,
            "volume": 2_500_000, "vwap": 99.94, "trades": 37}]
    records = list(adapt_bog_hdat_json(json.dumps(doc).encode("utf-8")))
    assert len(records) == 1
    r = records[0]
    assert r.bar_interval == "1d"
    assert r.open == 99.85
    assert r.trades_count == 37
    assert r.exchange == "BOG-HDAT"
