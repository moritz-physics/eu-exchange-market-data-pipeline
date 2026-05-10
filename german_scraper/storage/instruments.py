"""Instrument-master reference data.

Every silver record carries an ``isin`` (or another identifier). For
research it's almost always more useful to also have ticker, FIGI,
asset class, issuer country, and trading currency available without
a join. This module ingests a small CSV of reference data and offers
an ``enrich`` helper that fills missing fields on a record before write.

Why CSV (not OpenFIGI live):
    * No external dependency at ingest time.
    * Reproducibility: the reference snapshot is checked into the repo
      (or the warehouse) and versioned alongside the data.
    * Speed: a few hundred thousand instruments fit in RAM as a dict.

The CSV format is minimal:
    isin,ticker,figi,asset_class,country,currency

Empty cells are allowed. Lookups are by ISIN, then by ticker.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from german_scraper.core.logging_config import get_logger
from german_scraper.storage.schema import SilverRecord

logger = get_logger(__name__)


@dataclass(frozen=True)
class InstrumentRef:
    """One row from the instrument-master file."""

    isin: Optional[str] = None
    ticker: Optional[str] = None
    figi: Optional[str] = None
    asset_class: Optional[str] = None
    country: Optional[str] = None
    currency: Optional[str] = None


class InstrumentMaster:
    """In-memory lookup table over an instrument-master CSV.

    Lookup order: ISIN exact → ticker exact → FIGI exact. The first
    match wins. Repeat lookups for the same key are O(1).
    """

    def __init__(self) -> None:
        self._by_isin: dict[str, InstrumentRef] = {}
        self._by_ticker: dict[str, InstrumentRef] = {}
        self._by_figi: dict[str, InstrumentRef] = {}

    @classmethod
    def from_csv(cls, path: Path | str) -> "InstrumentMaster":
        """Load a master file. ``path`` may be missing — returns empty."""
        m = cls()
        p = Path(path)
        if not p.exists():
            logger.warning("Instrument master %s not found; lookups will return None", p)
            return m
        with p.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            n = 0
            for row in reader:
                ref = InstrumentRef(
                    isin=(row.get("isin") or "").strip() or None,
                    ticker=(row.get("ticker") or "").strip() or None,
                    figi=(row.get("figi") or "").strip() or None,
                    asset_class=(row.get("asset_class") or "").strip() or None,
                    country=(row.get("country") or "").strip() or None,
                    currency=(row.get("currency") or "").strip() or None,
                )
                if ref.isin:
                    m._by_isin[ref.isin] = ref
                if ref.ticker:
                    m._by_ticker[ref.ticker] = ref
                if ref.figi:
                    m._by_figi[ref.figi] = ref
                n += 1
        logger.info("Loaded %d instruments from %s", n, p)
        return m

    def lookup(
        self,
        *, isin: Optional[str] = None, ticker: Optional[str] = None,
        figi: Optional[str] = None,
    ) -> Optional[InstrumentRef]:
        """Return the first matching :class:`InstrumentRef` or ``None``."""
        if isin and isin in self._by_isin:
            return self._by_isin[isin]
        if ticker and ticker in self._by_ticker:
            return self._by_ticker[ticker]
        if figi and figi in self._by_figi:
            return self._by_figi[figi]
        return None

    def enrich(self, records: Iterable[SilverRecord]) -> int:
        """Fill in missing identifier / classification fields in-place.

        Only writes a field when the record's value is ``None`` so the
        adapter's choice always wins. Returns the number of records that
        had at least one field filled.
        """
        n = 0
        for r in records:
            ref = self.lookup(isin=r.isin, ticker=r.ticker, figi=r.figi)
            if ref is None:
                continue
            touched = False
            if r.isin is None and ref.isin:
                r.isin = ref.isin; touched = True
            if r.ticker is None and ref.ticker:
                r.ticker = ref.ticker; touched = True
            if r.figi is None and ref.figi:
                r.figi = ref.figi; touched = True
            if r.instrument_type is None and ref.asset_class:
                r.instrument_type = ref.asset_class; touched = True
            if r.currency is None and ref.currency:
                r.currency = ref.currency; touched = True
            if touched:
                n += 1
        return n


__all__ = ["InstrumentMaster", "InstrumentRef"]
