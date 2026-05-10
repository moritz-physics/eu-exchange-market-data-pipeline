"""Production-grade storage layer for the EU exchange scraper.

Public surface:

    DRY_RUN                       – module-level flag mirroring the env var
    StorageConfig / get_default_writer
    SCHEMA_VERSION                – pinned via storage/schema.py

    Records:
        TradeRecord, QuoteRecord, BarRecord
        SilverRecord                  (= TradeRecord | QuoteRecord | BarRecord)
        DataType, TradeFlag

    Schemas:
        TRADES_SCHEMA, QUOTES_SCHEMA, BARS_SCHEMA, SCHEMAS
        UNIFIED_SCHEMA, UnifiedRecord (back-compat aliases for older code)

    Backends:
        StorageBackend, LocalBackend, NFSBackend, S3Backend

    Writer:
        ParquetWriter

    Adapters:
        adapt_rts13_csv, adapt_bme_posttrade_json, adapt_bog_hdat_json
"""
from __future__ import annotations

from german_scraper.storage.adapters import (
    adapt_bme_posttrade_json,
    adapt_bog_hdat_json,
    adapt_rts13_csv,
    canonical_trade_flag,
)
from german_scraper.storage.backends import (
    LocalBackend,
    NFSBackend,
    S3Backend,
    StorageBackend,
)
from german_scraper.storage.config import DRY_RUN, StorageConfig, get_default_writer
from german_scraper.storage.parquet_writer import ParquetWriter
from german_scraper.storage.schema import (
    BARS_SCHEMA,
    BarRecord,
    DataType,
    QUOTES_SCHEMA,
    QuoteRecord,
    SCHEMA_VERSION,
    SCHEMAS,
    SilverRecord,
    TRADES_SCHEMA,
    TradeFlag,
    TradeRecord,
    UNIFIED_SCHEMA,
    UnifiedRecord,
    records_to_table,
)

__all__ = [
    "BARS_SCHEMA",
    "BarRecord",
    "DRY_RUN",
    "DataType",
    "LocalBackend",
    "NFSBackend",
    "ParquetWriter",
    "QUOTES_SCHEMA",
    "QuoteRecord",
    "S3Backend",
    "SCHEMA_VERSION",
    "SCHEMAS",
    "SilverRecord",
    "StorageBackend",
    "StorageConfig",
    "TRADES_SCHEMA",
    "TradeFlag",
    "TradeRecord",
    "UNIFIED_SCHEMA",
    "UnifiedRecord",
    "adapt_bme_posttrade_json",
    "adapt_bog_hdat_json",
    "adapt_rts13_csv",
    "canonical_trade_flag",
    "get_default_writer",
    "records_to_table",
]
