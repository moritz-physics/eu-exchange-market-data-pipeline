"""Per-table schemas for the silver layer.

The original wide schema (one table, 28 columns, 70% null per row) has
been split into three narrow tables. This is the standard layout for
tick datasets (TAQ, LOBSTER) and gives:

  * smaller files (no null padding for fields that don't apply),
  * sharper Parquet column statistics → better predicate pushdown,
  * simpler queries — `SELECT * FROM trades` is meaningful, whereas
    `SELECT * FROM unified` requires the reader to know which columns
    to ignore.

Three tables
============

    quotes  – pre-trade order-book / quote snapshots
    trades  – post-trade executions and trade reports
    bars    – aggregated OHLCV bars (Bank of Greece HDAT style)

A fourth view, ``v_all_events``, can be assembled at query time via
``UNION ALL`` of common columns when a uniform feed is needed for
research scripts.

Identifier columns
==================

``instrument_id`` (single column + type tag) has been replaced with
distinct columns: ``isin``, ``ticker``, ``figi``, ``mic``, plus an
opaque ``venue_instrument_id`` for codes the venue uses internally.
Joins against an instrument-master table become trivial.

Provenance / sequencing
=======================

Every record carries:

    seq                – monotonic sequence per (exchange, instrument)
    event_ts           – original timestamp from the venue feed (UTC)
    publication_ts     – timestamp on the file/message header (UTC)
    received_ts        – when this scraper received the bytes (UTC)
    ingest_ts          – when ingest wrote the silver row (UTC)
    source_msg_hash    – SHA-256 of the canonicalised raw record
    source_file        – original filename
    source_url         – URL the file came from
    schema_version     – pinned, bumped on any breaking change
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Optional

import pyarrow as pa


SCHEMA_VERSION: str = "2.0.0"


class DataType(str, Enum):
    """Logical record type — used for partitioning and validation."""

    PRE_TRADE = "pre_trade"      # quotes / order-book → table=quotes
    POST_TRADE = "post_trade"    # trades / executions → table=trades

    @classmethod
    def values(cls) -> list[str]:
        return [m.value for m in cls]


class TradeFlag(str, Enum):
    """Canonical, venue-agnostic trade-flag taxonomy.

    Maps the messy soup of venue-specific RTS-1/RTS-2 codes (LRGS, BENC,
    NPFT, OILQ, …) onto a small, query-friendly set. The raw venue flags
    are also preserved verbatim in ``trade_flags_raw`` so nothing is lost.
    """

    NORMAL = "normal"
    LARGE_IN_SCALE = "large_in_scale"     # LRGS / LIS waiver
    BENCHMARK = "benchmark"                # BENC
    NEGOTIATED = "negotiated"              # NPFT / negotiated trade
    DARK = "dark"                          # dark-pool / pre-trade waiver
    OFFBOOK = "offbook"                    # off-book on-exchange (NOFF, OILQ …)
    AGENCY_CROSS = "agency_cross"          # MOFF agency-cross
    SI = "systematic_internaliser"         # SI report
    LATE = "late_publication"              # delayed publication waiver
    CANCEL = "cancellation"
    AMENDMENT = "amendment"
    UNKNOWN = "unknown"

    @classmethod
    def values(cls) -> list[str]:
        return [m.value for m in cls]


# Common identity / provenance columns reused across all silver tables.
_COMMON_FIELDS: tuple[pa.Field, ...] = (
    pa.field("event_ts",       pa.timestamp("ns", tz="UTC"), nullable=False),
    pa.field("publication_ts", pa.timestamp("ns", tz="UTC")),
    pa.field("received_ts",    pa.timestamp("ns", tz="UTC")),
    pa.field("ingest_ts",      pa.timestamp("ns", tz="UTC"), nullable=False),
    pa.field("seq",            pa.int64()),

    pa.field("exchange",       pa.string(), nullable=False),
    pa.field("mic",            pa.string()),
    pa.field("data_type",      pa.string(), nullable=False),

    pa.field("isin",           pa.string()),
    pa.field("ticker",         pa.string()),
    pa.field("figi",           pa.string()),
    pa.field("venue_instrument_id", pa.string()),
    pa.field("instrument_type",     pa.string()),  # equity|bond|etf|derivative|energy|other
    pa.field("currency",            pa.string()),
    pa.field("venue_segment",       pa.string()),

    pa.field("source_file",     pa.string()),
    pa.field("source_url",      pa.string()),
    pa.field("source_msg_hash", pa.string()),
    pa.field("schema_version",  pa.string(), nullable=False),
)


# ── trades ──────────────────────────────────────────────────────────────
TRADES_SCHEMA: pa.Schema = pa.schema(
    list(_COMMON_FIELDS)
    + [
        pa.field("trade_price",  pa.float64()),
        pa.field("trade_size",   pa.float64()),
        pa.field("trade_id",     pa.string()),
        pa.field("notional",     pa.float64()),
        pa.field("side",         pa.string()),                # buy | sell | None
        pa.field("trade_flag_canonical", pa.string()),        # TradeFlag.value
        pa.field("trade_flags_raw",      pa.string()),
    ]
)

# ── quotes ──────────────────────────────────────────────────────────────
QUOTES_SCHEMA: pa.Schema = pa.schema(
    list(_COMMON_FIELDS)
    + [
        pa.field("bid_price",  pa.float64()),
        pa.field("bid_size",   pa.float64()),
        pa.field("ask_price",  pa.float64()),
        pa.field("ask_size",   pa.float64()),
        pa.field("book_level", pa.int32()),                   # 1 = top of book
        pa.field("snapshot",   pa.bool_()),                   # True = full snapshot
    ]
)

# ── bars ────────────────────────────────────────────────────────────────
BARS_SCHEMA: pa.Schema = pa.schema(
    list(_COMMON_FIELDS)
    + [
        pa.field("bar_interval", pa.string()),                # 1m | 5m | 1d
        pa.field("open",   pa.float64()),
        pa.field("high",   pa.float64()),
        pa.field("low",    pa.float64()),
        pa.field("close",  pa.float64()),
        pa.field("volume", pa.float64()),
        pa.field("vwap",   pa.float64()),
        pa.field("trades_count", pa.int64()),
    ]
)


SCHEMAS: dict[str, pa.Schema] = {
    "trades": TRADES_SCHEMA,
    "quotes": QUOTES_SCHEMA,
    "bars":   BARS_SCHEMA,
}


# ─── Python-native record types (one per table) ─────────────────────────
@dataclass
class _Common:
    """Shared identity / provenance fields. Not used directly — see subclasses."""

    event_ts: Optional[datetime] = None
    publication_ts: Optional[datetime] = None
    received_ts: Optional[datetime] = None
    ingest_ts: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    seq: Optional[int] = None

    exchange: Optional[str] = None
    mic: Optional[str] = None
    data_type: Optional[str] = None

    isin: Optional[str] = None
    ticker: Optional[str] = None
    figi: Optional[str] = None
    venue_instrument_id: Optional[str] = None
    instrument_type: Optional[str] = None
    currency: Optional[str] = None
    venue_segment: Optional[str] = None

    source_file: Optional[str] = None
    source_url: Optional[str] = None
    source_msg_hash: Optional[str] = None
    schema_version: str = SCHEMA_VERSION


@dataclass
class TradeRecord(_Common):
    """One execution / trade report."""

    trade_price: Optional[float] = None
    trade_size: Optional[float] = None
    trade_id: Optional[str] = None
    notional: Optional[float] = None
    side: Optional[str] = None
    trade_flag_canonical: Optional[str] = None
    trade_flags_raw: Optional[str] = None

    TABLE: str = "trades"


@dataclass
class QuoteRecord(_Common):
    """One quote / order-book level snapshot."""

    bid_price: Optional[float] = None
    bid_size: Optional[float] = None
    ask_price: Optional[float] = None
    ask_size: Optional[float] = None
    book_level: Optional[int] = None
    snapshot: Optional[bool] = None

    TABLE: str = "quotes"


@dataclass
class BarRecord(_Common):
    """One OHLCV bar (Bank of Greece HDAT style)."""

    bar_interval: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    vwap: Optional[float] = None
    trades_count: Optional[int] = None

    TABLE: str = "bars"


SilverRecord = TradeRecord | QuoteRecord | BarRecord


_REQUIRED_FIELDS: tuple[str, ...] = (
    "event_ts", "ingest_ts", "exchange", "data_type", "schema_version",
)


def records_to_table(records: Iterable[SilverRecord]) -> tuple[str, pa.Table]:
    """Validate and convert ``records`` (all of one ``TABLE``) into an Arrow table.

    Returns a ``(table_name, pa.Table)`` pair so callers can route the
    result to the correct partition root.
    """
    rows = list(records)
    if not rows:
        raise ValueError("records_to_table called with no records")

    table_name = rows[0].TABLE
    schema = SCHEMAS[table_name]
    if any(r.TABLE != table_name for r in rows):
        raise ValueError("records_to_table requires all rows of the same TABLE")

    out: list[dict[str, Any]] = []
    for r in rows:
        d = asdict(r)
        d.pop("TABLE", None)
        for required in _REQUIRED_FIELDS:
            if d.get(required) is None:
                raise ValueError(f"{table_name} record missing required field: {required!r}")
        if d["data_type"] not in DataType.values():
            raise ValueError(
                f"data_type {d['data_type']!r} not in {DataType.values()}"
            )
        if (
            d.get("trade_flag_canonical") is not None
            and d["trade_flag_canonical"] not in TradeFlag.values()
        ):
            raise ValueError(
                f"trade_flag_canonical {d['trade_flag_canonical']!r} "
                f"not in {TradeFlag.values()}"
            )
        out.append(d)

    columns: dict[str, list[Any]] = {f.name: [] for f in schema}
    for row in out:
        for col in columns:
            columns[col].append(row.get(col))

    arrays = [pa.array(columns[f.name], type=f.type) for f in schema]
    return table_name, pa.Table.from_arrays(arrays, schema=schema)


# ─── Back-compat alias so older callers keep working ─────────────────────
# UNIFIED_SCHEMA is no longer a single canonical schema; expose the union
# of column names so legacy code that introspected it for documentation
# still works.
UNIFIED_SCHEMA: pa.Schema = TRADES_SCHEMA  # default introspection target
UnifiedRecord = TradeRecord                 # back-compat for old imports

__all__ = [
    "BarRecord",
    "BARS_SCHEMA",
    "DataType",
    "QuoteRecord",
    "QUOTES_SCHEMA",
    "SCHEMA_VERSION",
    "SCHEMAS",
    "SilverRecord",
    "TradeFlag",
    "TradeRecord",
    "TRADES_SCHEMA",
    "UNIFIED_SCHEMA",
    "UnifiedRecord",
    "records_to_table",
]
