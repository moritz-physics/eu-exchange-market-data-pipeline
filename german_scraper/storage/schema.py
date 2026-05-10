"""Unified Parquet schema for every record this pipeline produces.

Why a single schema across all exchanges:
    Pre- and post-trade data from EU exchanges arrive in heterogeneous
    formats (CSV, JSON, JSON.GZ, ZIP, …). For downstream research we want a
    single columnar dataset that can be queried with pandas, DuckDB, or
    Spark without per-exchange parsing.

The schema is wide enough to accommodate quotes, trades, OHLCV bars, and
order-book snapshots. Fields not relevant to a given record are left null;
columnar storage compresses nulls efficiently so this is cheap.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Optional

import pyarrow as pa


class DataType(str, Enum):
    """Whether a record is pre-trade (orders/quotes) or post-trade (executions)."""

    PRE_TRADE = "pre_trade"
    POST_TRADE = "post_trade"

    @classmethod
    def values(cls) -> list[str]:
        return [m.value for m in cls]


# Single source of truth for the columnar schema.
#
# Partition columns (exchange, year, month, day, instrument_type) are also
# stored *inside* the row group so the dataset remains self-describing if
# files are ever moved out of their partition directories.
UNIFIED_SCHEMA: pa.Schema = pa.schema(
    [
        # ── identity / partition columns ─────────────────────────────────
        pa.field("event_ts", pa.timestamp("ns", tz="UTC"), nullable=False),
        pa.field("ingest_ts", pa.timestamp("ns", tz="UTC"), nullable=False),
        pa.field("exchange", pa.string(), nullable=False),
        pa.field("mic", pa.string()),                        # ISO 10383 Market Identifier Code
        pa.field("data_type", pa.string(), nullable=False),  # pre_trade | post_trade
        pa.field("instrument_type", pa.string()),            # equity | bond | etf | derivative | energy | other
        pa.field("instrument_id", pa.string()),              # ISIN, ticker, or contract code
        pa.field("instrument_id_type", pa.string()),         # ISIN | TICKER | FIGI | INTERNAL
        pa.field("currency", pa.string()),                   # ISO 4217
        pa.field("venue_segment", pa.string()),              # MTF segment / sub-market

        # ── pre-trade fields (quotes, order book) ───────────────────────
        pa.field("bid_price", pa.float64()),
        pa.field("bid_size", pa.float64()),
        pa.field("ask_price", pa.float64()),
        pa.field("ask_size", pa.float64()),
        pa.field("book_level", pa.int32()),                  # 1 = top of book

        # ── post-trade fields (executions) ──────────────────────────────
        pa.field("trade_price", pa.float64()),
        pa.field("trade_size", pa.float64()),
        pa.field("trade_id", pa.string()),
        pa.field("notional", pa.float64()),
        pa.field("trade_flags", pa.string()),                # raw venue flags string

        # ── OHLCV bars (when reported as bars rather than ticks) ────────
        pa.field("open", pa.float64()),
        pa.field("high", pa.float64()),
        pa.field("low", pa.float64()),
        pa.field("close", pa.float64()),
        pa.field("volume", pa.float64()),

        # ── lineage ─────────────────────────────────────────────────────
        pa.field("source_file", pa.string()),                # filename of raw payload
        pa.field("source_url", pa.string()),                 # original URL
        pa.field("schema_version", pa.string(), nullable=False),
    ]
)

SCHEMA_VERSION: str = "1.0.0"


@dataclass
class UnifiedRecord:
    """Python-native mirror of :data:`UNIFIED_SCHEMA`.

    All fields default to ``None`` so adapters only fill in what the source
    payload actually provides. Required fields are validated by
    :func:`records_to_table` at write time.
    """

    event_ts: Optional[datetime] = None
    ingest_ts: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    exchange: Optional[str] = None
    mic: Optional[str] = None
    data_type: Optional[str] = None
    instrument_type: Optional[str] = None
    instrument_id: Optional[str] = None
    instrument_id_type: Optional[str] = None
    currency: Optional[str] = None
    venue_segment: Optional[str] = None

    bid_price: Optional[float] = None
    bid_size: Optional[float] = None
    ask_price: Optional[float] = None
    ask_size: Optional[float] = None
    book_level: Optional[int] = None

    trade_price: Optional[float] = None
    trade_size: Optional[float] = None
    trade_id: Optional[str] = None
    notional: Optional[float] = None
    trade_flags: Optional[str] = None

    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None

    source_file: Optional[str] = None
    source_url: Optional[str] = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_REQUIRED_FIELDS: tuple[str, ...] = (
    "event_ts", "ingest_ts", "exchange", "data_type", "schema_version",
)


def records_to_table(records: Iterable[UnifiedRecord]) -> pa.Table:
    """Convert an iterable of :class:`UnifiedRecord` into a typed Arrow table.

    Validates that required fields are present and that ``data_type`` is one
    of :class:`DataType`.
    """
    rows: list[dict[str, Any]] = []
    for r in records:
        d = r.to_dict()
        for required in _REQUIRED_FIELDS:
            if d.get(required) is None:
                raise ValueError(f"UnifiedRecord missing required field: {required!r}")
        if d["data_type"] not in DataType.values():
            raise ValueError(
                f"data_type {d['data_type']!r} not in {DataType.values()}"
            )
        rows.append(d)

    if not rows:
        return UNIFIED_SCHEMA.empty_table()

    columns: dict[str, list[Any]] = {f.name: [] for f in UNIFIED_SCHEMA}
    for row in rows:
        for col in columns:
            columns[col].append(row.get(col))

    arrays = []
    for f in UNIFIED_SCHEMA:
        arrays.append(pa.array(columns[f.name], type=f.type))
    return pa.Table.from_arrays(arrays, schema=UNIFIED_SCHEMA)
