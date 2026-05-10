"""Partitioned Parquet writer with Snappy compression and DRY_RUN simulation.

Layout written to the configured backend:
    data/exchange={exchange}/year={YYYY}/month={MM}/day={DD}/instrument_type={t}/{data_type}.parquet

Why Parquet + Snappy:
    Columnar layout, predicate pushdown, splittable, supported natively by
    pandas, polars, DuckDB, Spark, Trino. Snappy gives the best
    decompression speed for the size-vs-CPU trade-off this workload sees;
    ZSTD compresses better but takes ~3× longer to read.
"""
from __future__ import annotations

import io
import os
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable

import pyarrow as pa
import pyarrow.parquet as pq

from german_scraper.core.logging_config import get_logger
from german_scraper.storage.backends import StorageBackend
from german_scraper.storage.schema import (
    UNIFIED_SCHEMA,
    UnifiedRecord,
    records_to_table,
)

logger = get_logger(__name__)


def _coerce_partition_value(value: Any, default: str = "unknown") -> str:
    """Stringify a partition column, replacing path-unsafe characters."""
    if value is None or value == "":
        return default
    s = str(value)
    return (
        s.replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
        .replace("=", "_")
    )


def _partition_key(record: UnifiedRecord) -> tuple[str, str, str, str, str, str]:
    """Return ``(exchange, year, month, day, instrument_type, data_type)``."""
    if record.event_ts is None:
        raise ValueError("UnifiedRecord.event_ts is required for partitioning")
    ts: datetime = record.event_ts
    return (
        _coerce_partition_value(record.exchange),
        f"{ts.year:04d}",
        f"{ts.month:02d}",
        f"{ts.day:02d}",
        _coerce_partition_value(record.instrument_type, default="unknown"),
        _coerce_partition_value(record.data_type),
    )


def _partition_path(parts: tuple[str, str, str, str, str, str]) -> str:
    exchange, year, month, day, instr, data_type = parts
    return (
        f"exchange={exchange}/year={year}/month={month}/day={day}/"
        f"instrument_type={instr}/{data_type}.parquet"
    )


class ParquetWriter:
    """Group records by partition and write them as Parquet.

    Designed for batch ingestion: pass a full batch of records, get back a
    list of written URIs. In DRY_RUN mode the writer instead prints a
    detailed simulation report (one block per partition).
    """

    def __init__(
        self,
        backend: StorageBackend,
        *,
        compression: str = "snappy",
        row_group_size: int = 64 * 1024,
        dry_run: bool | None = None,
        data_root_key: str = "data",
    ) -> None:
        self.backend = backend
        self.compression = compression
        self.row_group_size = row_group_size
        self.data_root_key = data_root_key.strip("/")

        # Allow per-instance override; default falls back to module-level config.
        if dry_run is None:
            from german_scraper.storage.config import DRY_RUN as _DRY
            dry_run = _DRY
        self.dry_run = dry_run

    def _full_key(self, partition_path: str) -> str:
        return f"{self.data_root_key}/{partition_path}"

    def _serialise(self, table: pa.Table) -> bytes:
        buf = io.BytesIO()
        pq.write_table(
            table,
            buf,
            compression=self.compression,
            row_group_size=self.row_group_size,
            use_dictionary=True,
            data_page_version="2.0",
        )
        return buf.getvalue()

    def write(self, records: Iterable[UnifiedRecord]) -> list[str]:
        """Write ``records`` grouped by partition.

        Returns the list of URIs that *would* be written (DRY_RUN) or were
        written (live mode). Always validates the schema first, even in
        dry-run mode, so the simulation matches reality.
        """
        records = list(records)
        if not records:
            logger.info("ParquetWriter.write called with 0 records — no-op")
            return []

        groups: dict[tuple, list[UnifiedRecord]] = defaultdict(list)
        for r in records:
            groups[_partition_key(r)].append(r)

        if self.dry_run:
            return self._simulate(groups)

        written: list[str] = []
        for parts, group_records in groups.items():
            table = records_to_table(group_records)
            payload = self._serialise(table)
            key = self._full_key(_partition_path(parts))
            uri = self.backend.write_bytes(key, payload)
            logger.info(
                "Wrote %d rows (%d compressed bytes) → %s",
                table.num_rows, len(payload), uri,
            )
            written.append(uri)
        return written

    # ── DRY_RUN simulation ──────────────────────────────────────────────
    def _simulate(self, groups: dict[tuple, list[UnifiedRecord]]) -> list[str]:
        """Print a detailed simulation report and return synthetic URIs."""
        backend_label = f"{self.backend.name}://{getattr(self.backend, 'root', getattr(self.backend, 'bucket', '?'))}"
        line = "═" * 78
        out: list[str] = []
        print(f"\n{line}")
        print("DRY-RUN SIMULATION  ·  ParquetWriter")
        print(line)
        print(f"  backend          : {backend_label}")
        print(f"  compression      : {self.compression}")
        print(f"  row_group_size   : {self.row_group_size}")
        print(f"  partitions       : {len(groups)}")
        print(f"  total records    : {sum(len(v) for v in groups.values())}")
        print(f"  schema columns   : {len(UNIFIED_SCHEMA)}")
        print(line)

        for parts, group_records in groups.items():
            table = records_to_table(group_records)
            partition_path = _partition_path(parts)
            uri = f"{backend_label}/{self._full_key(partition_path)}"

            payload = self._serialise(table)
            est_size = len(payload)

            print(f"\n▸ Partition: {partition_path}")
            print(f"    rows               : {table.num_rows}")
            print(f"    estimated size     : {est_size:,} bytes ({est_size/1024:.1f} KiB)")
            print(f"    target URI         : {uri}")
            print(f"    schema (col : dtype):")
            for f in UNIFIED_SCHEMA:
                print(f"      - {f.name:22s} {f.type}")

            print(f"    sample rows (head 5):")
            head = table.slice(0, 5).to_pydict()
            for i in range(min(5, table.num_rows)):
                row_repr = ", ".join(
                    f"{c}={head[c][i]}" for c in (
                        "event_ts", "exchange", "data_type", "instrument_id",
                        "trade_price", "bid_price", "ask_price", "trade_size",
                    ) if c in head
                )
                print(f"      [{i}] {row_repr}")

            out.append(uri)

        print(f"\n{line}")
        print("DRY_RUN=True  →  no bytes were written to {}.".format(self.backend.name))
        print(f"{line}\n")
        return out


__all__ = ["ParquetWriter"]
