"""Production-grade storage layer for the EU exchange scraper.

Public surface:
    - DRY_RUN flag (configurable via env, defaults to True)
    - UNIFIED_SCHEMA          – pyarrow Schema for all records
    - DataType                 – PRE_TRADE / POST_TRADE enum
    - UnifiedRecord            – dataclass mirror of UNIFIED_SCHEMA
    - StorageBackend           – abstract; LocalBackend / S3Backend / NFSBackend
    - ParquetWriter            – partitioned writer with DRY_RUN simulation
    - get_default_writer()     – factory honouring env-based config
"""
from __future__ import annotations

from german_scraper.storage.config import DRY_RUN, StorageConfig, get_default_writer
from german_scraper.storage.schema import (
    DataType,
    UNIFIED_SCHEMA,
    UnifiedRecord,
    records_to_table,
)
from german_scraper.storage.backends import (
    LocalBackend,
    NFSBackend,
    S3Backend,
    StorageBackend,
)
from german_scraper.storage.parquet_writer import ParquetWriter

__all__ = [
    "DRY_RUN",
    "DataType",
    "LocalBackend",
    "NFSBackend",
    "ParquetWriter",
    "S3Backend",
    "StorageBackend",
    "StorageConfig",
    "UNIFIED_SCHEMA",
    "UnifiedRecord",
    "get_default_writer",
    "records_to_table",
]
