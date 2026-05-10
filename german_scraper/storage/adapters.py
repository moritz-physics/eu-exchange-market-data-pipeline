"""Per-payload adapters that turn raw bytes into typed silver records.

Each adapter:
    * decodes the raw payload (CSV / JSON / …),
    * normalises timestamps to UTC,
    * resolves identifiers (ISIN preferred; falls back to venue code),
    * canonicalises trade flags via :class:`TradeFlag`,
    * computes ``source_msg_hash`` per record so dedupe works post-ingest,
    * yields :class:`TradeRecord`, :class:`QuoteRecord`, or
      :class:`BarRecord` instances.

The adapters here are demonstrative; one per native format. Wire a new
exchange by adding a function that returns the right record type.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from typing import Iterator, Optional

from german_scraper.storage.schema import (
    BarRecord,
    DataType,
    QuoteRecord,
    TradeFlag,
    TradeRecord,
)


# ── canonical trade-flag mapping ────────────────────────────────────────
_RAW_TO_CANONICAL: dict[str, TradeFlag] = {
    # MiFIR RTS-1 / RTS-2 codes that show up in delayed-data feeds
    "LRGS": TradeFlag.LARGE_IN_SCALE,
    "LIS":  TradeFlag.LARGE_IN_SCALE,
    "BENC": TradeFlag.BENCHMARK,
    "NPFT": TradeFlag.NEGOTIATED,
    "NLIQ": TradeFlag.NEGOTIATED,
    "OILQ": TradeFlag.OFFBOOK,
    "NOFF": TradeFlag.OFFBOOK,
    "MOFF": TradeFlag.AGENCY_CROSS,
    "DARK": TradeFlag.DARK,
    "RFPT": TradeFlag.DARK,
    "SI":   TradeFlag.SI,
    "SDIV": TradeFlag.SI,
    "DLAY": TradeFlag.LATE,
    "CANC": TradeFlag.CANCEL,
    "AMND": TradeFlag.AMENDMENT,
}


def canonical_trade_flag(raw: Optional[str]) -> Optional[str]:
    """Best-effort mapping of a venue's RTS-1/RTS-2 flag to TradeFlag.value.

    Multi-flag fields (``"LRGS,BENC"``) collapse to the highest-priority
    flag in the order LARGE_IN_SCALE → BENCHMARK → NEGOTIATED → DARK →
    SI → OFFBOOK → AGENCY_CROSS → LATE → CANCEL → AMENDMENT, falling
    through to NORMAL if the field is empty or to UNKNOWN if no token
    matches.
    """
    if raw is None or str(raw).strip() == "":
        return TradeFlag.NORMAL.value
    tokens = [t.strip().upper() for t in str(raw).replace(";", ",").split(",") if t.strip()]
    if not tokens:
        return TradeFlag.NORMAL.value
    priority = [
        TradeFlag.LARGE_IN_SCALE, TradeFlag.BENCHMARK, TradeFlag.NEGOTIATED,
        TradeFlag.DARK, TradeFlag.SI, TradeFlag.OFFBOOK,
        TradeFlag.AGENCY_CROSS, TradeFlag.LATE,
        TradeFlag.CANCEL, TradeFlag.AMENDMENT,
    ]
    matches = {_RAW_TO_CANONICAL.get(t) for t in tokens}
    matches.discard(None)
    for flag in priority:
        if flag in matches:
            return flag.value
    return TradeFlag.UNKNOWN.value


def _safe_float(value: object) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_ts_utc(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts.astimezone(timezone.utc) if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _row_hash(*parts: object) -> str:
    """Deterministic per-row hash for dedupe."""
    blob = "|".join("" if p is None else str(p) for p in parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ── ATHEX / Boerse Berlin RTS-13 style CSVs → trades ────────────────────
def adapt_rts13_csv(
    payload: bytes,
    *,
    exchange: str,
    mic: str | None = None,
    data_type: DataType = DataType.POST_TRADE,
    source_file: str | None = None,
    source_url: str | None = None,
) -> Iterator[TradeRecord]:
    """Parse a generic RTS-13 trade-data CSV into :class:`TradeRecord`s."""
    text = payload.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return
    columns = {c.lower(): c for c in reader.fieldnames}

    def col(row: dict, *names: str) -> Optional[str]:
        for n in names:
            real = columns.get(n.lower())
            if real and row.get(real) not in (None, ""):
                return row[real]
        return None

    received_ts = datetime.now(tz=timezone.utc)
    seq = 0
    for row in reader:
        event_ts = _parse_ts_utc(col(row, "TradingDateTime", "Timestamp", "TradeTime"))
        if event_ts is None:
            continue
        seq += 1
        price = _safe_float(col(row, "Price"))
        size = _safe_float(col(row, "Quantity"))
        flags_raw = col(row, "Flags")
        isin = col(row, "ISIN")

        yield TradeRecord(
            event_ts=event_ts,
            received_ts=received_ts,
            seq=seq,
            exchange=exchange,
            mic=mic,
            data_type=data_type.value,
            isin=isin,
            instrument_type="equity",
            currency=col(row, "Currency"),
            trade_price=price,
            trade_size=size,
            trade_id=col(row, "TradeID", "TransactionID"),
            notional=(price * size) if (price and size) else None,
            trade_flags_raw=flags_raw,
            trade_flag_canonical=canonical_trade_flag(flags_raw),
            source_file=source_file,
            source_url=source_url,
            source_msg_hash=_row_hash(exchange, isin, event_ts, price, size, flags_raw),
        )


# ── BME post-trade JSON → trades ────────────────────────────────────────
def adapt_bme_posttrade_json(
    payload: bytes,
    *,
    source_file: str | None = None,
    source_url: str | None = None,
) -> Iterator[TradeRecord]:
    """Parse BME (Spain) ``*_BMEA_posttrade.json`` files."""
    try:
        doc = json.loads(payload.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return
    rows = doc if isinstance(doc, list) else doc.get("trades") or doc.get("data") or []
    received_ts = datetime.now(tz=timezone.utc)
    seq = 0

    for row in rows:
        event_ts = _parse_ts_utc(
            row.get("trading_datetime")
            or row.get("tradingDateTime")
            or row.get("timestamp")
        )
        if event_ts is None:
            continue
        seq += 1
        price = _safe_float(row.get("price") or row.get("Price"))
        size = _safe_float(row.get("volume") or row.get("quantity"))
        isin = row.get("isin") or row.get("ISIN")
        flags_raw = row.get("flags") or row.get("Flags")

        yield TradeRecord(
            event_ts=event_ts,
            received_ts=received_ts,
            seq=seq,
            exchange="BME",
            mic="BMEX",
            data_type=DataType.POST_TRADE.value,
            isin=isin,
            instrument_type="equity",
            currency=row.get("currency") or row.get("Currency"),
            trade_price=price,
            trade_size=size,
            trade_id=row.get("trade_id") or row.get("TradeID"),
            notional=(price * size) if (price and size) else None,
            trade_flags_raw=flags_raw,
            trade_flag_canonical=canonical_trade_flag(flags_raw),
            source_file=source_file,
            source_url=source_url,
            source_msg_hash=_row_hash("BME", isin, event_ts, price, size, flags_raw),
        )


# ── Bank of Greece HDAT JSON → bars ─────────────────────────────────────
def adapt_bog_hdat_json(
    payload: bytes,
    *,
    data_type: DataType = DataType.POST_TRADE,
    source_file: str | None = None,
    source_url: str | None = None,
) -> Iterator[BarRecord]:
    """Parse a Bank of Greece HDAT JSON file as daily OHLCV bars."""
    try:
        doc = json.loads(payload.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return
    rows = doc if isinstance(doc, list) else doc.get("data") or []
    received_ts = datetime.now(tz=timezone.utc)

    for row in rows:
        event_ts = _parse_ts_utc(row.get("date") or row.get("session_date"))
        if event_ts is None:
            continue
        isin = row.get("isin") or row.get("ISIN")
        yield BarRecord(
            event_ts=event_ts,
            received_ts=received_ts,
            exchange="BOG-HDAT",
            mic="HDAT",
            data_type=data_type.value,
            isin=isin,
            instrument_type="bond",
            currency="EUR",
            bar_interval="1d",
            open=_safe_float(row.get("open")),
            high=_safe_float(row.get("high")),
            low=_safe_float(row.get("low")),
            close=_safe_float(row.get("close")),
            volume=_safe_float(row.get("volume")),
            vwap=_safe_float(row.get("vwap")),
            trades_count=int(row["trades"]) if row.get("trades") else None,
            source_file=source_file,
            source_url=source_url,
            source_msg_hash=_row_hash("BOG-HDAT", isin, event_ts, row.get("close")),
        )


__all__ = [
    "adapt_bme_posttrade_json",
    "adapt_bog_hdat_json",
    "adapt_rts13_csv",
    "canonical_trade_flag",
]
