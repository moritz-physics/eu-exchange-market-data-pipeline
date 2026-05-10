"""Adapters that transform raw exchange payloads into :class:`UnifiedRecord`.

This module is deliberately small and demonstrative: it shows how a new
exchange feed is plugged into the unified schema. The full set of adapters
covering every supported exchange lives alongside the scrapers in
``german_scraper/exchanges/`` (one ``parse_*`` helper per file, called by
the scraper after a download completes).

Each adapter takes the raw bytes plus minimal metadata (exchange code,
data type) and yields :class:`UnifiedRecord` instances. Adapters never
write — that's the writer's job.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Iterator

from german_scraper.storage.schema import DataType, UnifiedRecord


# ── ATHEX / Boerse Berlin RTS-13 style CSVs ─────────────────────────────
def adapt_rts13_csv(
    payload: bytes,
    *,
    exchange: str,
    mic: str | None = None,
    data_type: DataType = DataType.POST_TRADE,
    source_file: str | None = None,
) -> Iterator[UnifiedRecord]:
    """Parse a generic RTS-13 style trade-data CSV.

    Looks for these column names (case-insensitive): ``TradingDateTime``,
    ``ISIN``, ``Price``, ``Quantity``, ``Currency``, ``TradeID`` /
    ``TransactionID``, ``Flags``. Missing columns default to None — the
    schema accommodates partial payloads.
    """
    text = payload.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return
    columns = {c.lower(): c for c in reader.fieldnames}

    def col(row: dict, *names: str) -> str | None:
        for n in names:
            real = columns.get(n.lower())
            if real and row.get(real) not in (None, ""):
                return row[real]
        return None

    for row in reader:
        ts_raw = col(row, "TradingDateTime", "Timestamp", "TradeTime")
        try:
            event_ts = (
                datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                if ts_raw else None
            )
        except ValueError:
            event_ts = None
        if event_ts is None:
            continue
        if event_ts.tzinfo is None:
            event_ts = event_ts.replace(tzinfo=timezone.utc)
        else:
            event_ts = event_ts.astimezone(timezone.utc)

        def to_float(name: str) -> float | None:
            raw = col(row, name)
            try:
                return float(raw) if raw not in (None, "") else None
            except ValueError:
                return None

        yield UnifiedRecord(
            event_ts=event_ts,
            exchange=exchange,
            mic=mic,
            data_type=data_type.value,
            instrument_type="equity",
            instrument_id=col(row, "ISIN"),
            instrument_id_type="ISIN" if col(row, "ISIN") else None,
            currency=col(row, "Currency"),
            trade_price=to_float("Price"),
            trade_size=to_float("Quantity"),
            trade_id=col(row, "TradeID", "TransactionID"),
            trade_flags=col(row, "Flags"),
            source_file=source_file,
        )


# ── BME post-trade JSON ─────────────────────────────────────────────────
def adapt_bme_posttrade_json(
    payload: bytes,
    *,
    source_file: str | None = None,
) -> Iterator[UnifiedRecord]:
    """Parse BME (Spain) ``*_BMEA_posttrade.json`` files.

    BME publishes a JSON document whose top level is a list of trade
    records with ``isin``, ``price``, ``volume``, ``trading_datetime`` and
    ``currency`` fields. Field names vary slightly across releases; the
    adapter normalises common spellings.
    """
    try:
        doc = json.loads(payload.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return
    rows = doc if isinstance(doc, list) else doc.get("trades") or doc.get("data") or []

    for row in rows:
        ts_raw = (
            row.get("trading_datetime")
            or row.get("tradingDateTime")
            or row.get("timestamp")
        )
        if not ts_raw:
            continue
        try:
            event_ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if event_ts.tzinfo is None:
            event_ts = event_ts.replace(tzinfo=timezone.utc)
        else:
            event_ts = event_ts.astimezone(timezone.utc)

        yield UnifiedRecord(
            event_ts=event_ts,
            exchange="BME",
            mic="BMEX",
            data_type=DataType.POST_TRADE.value,
            instrument_type="equity",
            instrument_id=row.get("isin") or row.get("ISIN"),
            instrument_id_type="ISIN",
            currency=row.get("currency") or row.get("Currency"),
            trade_price=_safe_float(row.get("price") or row.get("Price")),
            trade_size=_safe_float(row.get("volume") or row.get("quantity")),
            trade_id=row.get("trade_id") or row.get("TradeID"),
            source_file=source_file,
        )


def _safe_float(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
