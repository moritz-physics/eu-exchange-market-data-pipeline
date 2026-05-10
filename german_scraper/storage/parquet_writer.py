"""Partitioned Parquet writer (silver layer).

Per-table writers — one for ``trades``, ``quotes``, ``bars`` — share a
common backend interface and partition layout:

    {table}/exchange={EX}/year={YYYY}/month={MM}/day={DD}/instrument_type={t}/part-{ts}.parquet

Why per-file rather than per-partition:
    Append-only writes to one Parquet file per partition is unsafe across
    runs (no atomic append). Instead each run produces a unique
    ``part-{epoch_ms}.parquet`` file inside the partition; a separate
    compaction job rolls them up. This is the same layout Iceberg / Delta
    use under the hood.

Every emitted file is registered in the SQLite manifest's ``silver``
table — gives downstream queries a fast catalog and the operator a
durable record of what was produced.
"""
from __future__ import annotations

import io
import time
from collections import defaultdict
from datetime import datetime
from typing import Iterable

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from german_scraper.core.logging_config import get_logger
from german_scraper.core.manifest_db import (
    DEFAULT_MANIFEST_PATH,
    Manifest,
    SilverRecord as ManifestSilverRecord,
    SilverStatus,
)
from german_scraper.storage.backends import StorageBackend
from german_scraper.storage.schema import (
    SCHEMAS,
    SilverRecord,
    records_to_table,
)

logger = get_logger(__name__)


def _coerce_partition_value(value: object, default: str = "unknown") -> str:
    if value is None or value == "":
        return default
    s = str(value)
    return (
        s.replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
        .replace("=", "_")
    )


def _partition_key(record: SilverRecord) -> tuple[str, str, str, str, str]:
    if record.event_ts is None:
        raise ValueError(f"{type(record).__name__}.event_ts is required for partitioning")
    ts: datetime = record.event_ts
    return (
        _coerce_partition_value(record.exchange),
        f"{ts.year:04d}",
        f"{ts.month:02d}",
        f"{ts.day:02d}",
        _coerce_partition_value(record.instrument_type, default="unknown"),
    )


def _partition_dir(table: str, parts: tuple[str, str, str, str, str]) -> str:
    exchange, year, month, day, instr = parts
    return (
        f"{table}/exchange={exchange}/year={year}/month={month}/day={day}/"
        f"instrument_type={instr}"
    )


class ParquetWriter:
    """Routes records into per-table partitions and serialises to Parquet.

    DRY_RUN mode replaces the backend write with a structured simulation
    report; the schema validation, partitioning, sorting, and serialisation
    paths run identically so the report matches reality.
    """

    def __init__(
        self,
        backend: StorageBackend,
        *,
        compression: str = "snappy",
        row_group_size: int = 64 * 1024,
        dry_run: bool | None = None,
        data_root_key: str = "data",
        manifest: Manifest | None = None,
    ) -> None:
        self.backend = backend
        self.compression = compression
        self.row_group_size = row_group_size
        self.data_root_key = data_root_key.strip("/")

        if dry_run is None:
            from german_scraper.storage.config import DRY_RUN as _DRY
            dry_run = _DRY
        self.dry_run = dry_run

        self.manifest = (
            manifest
            if manifest is not None
            else (Manifest(DEFAULT_MANIFEST_PATH) if not dry_run else None)
        )

    def _full_key(self, partition_path: str) -> str:
        return f"{self.data_root_key}/{partition_path}"

    @staticmethod
    def _sort_table(table: pa.Table) -> pa.Table:
        """Sort within partition by (event_ts, isin) to maximise stat pruning."""
        sort_keys: list[tuple[str, str]] = [("event_ts", "ascending")]
        if "isin" in table.column_names:
            sort_keys.append(("isin", "ascending"))
        # ``pyarrow.compute.sort_indices`` exists at runtime but is missing
        # from older type stubs; ``getattr`` keeps us strict-mode clean
        # without losing functionality.
        sort_indices = getattr(pc, "sort_indices")
        indices = sort_indices(table, sort_keys=sort_keys)
        return table.take(indices)

    def _serialise(self, table: pa.Table) -> bytes:
        buf = io.BytesIO()
        pq.write_table(
            table,
            buf,
            compression=self.compression,
            row_group_size=self.row_group_size,
            use_dictionary=True,
            data_page_version="2.0",
            write_statistics=True,
        )
        return buf.getvalue()

    def write(self, records: Iterable[SilverRecord]) -> list[str]:
        """Write ``records``, grouped by (table, partition).

        All records of one table are validated against that table's schema
        and sorted within partition before serialisation.
        """
        records = list(records)
        if not records:
            logger.info("ParquetWriter.write called with 0 records — no-op")
            return []

        # Group by (table_name, partition_key)
        groups: dict[tuple[str, tuple], list[SilverRecord]] = defaultdict(list)
        for r in records:
            groups[(r.TABLE, _partition_key(r))].append(r)

        if self.dry_run:
            return self._simulate(groups)

        written: list[str] = []
        run_ms = int(time.time() * 1000)
        for (table_name, parts), group_records in groups.items():
            _, table = records_to_table(group_records)
            table = self._sort_table(table)
            payload = self._serialise(table)

            partition_dir = _partition_dir(table_name, parts)
            file_name = f"part-{run_ms}-{abs(hash(parts)) % 100000:05d}.parquet"
            key = self._full_key(f"{partition_dir}/{file_name}")
            uri = self.backend.write_bytes(key, payload)

            logger.info(
                "Wrote %s: %d rows (%d bytes) → %s",
                table_name, table.num_rows, len(payload), uri,
            )
            written.append(uri)

            if self.manifest:
                self.manifest.record_silver(
                    ManifestSilverRecord(
                        table=table_name,
                        partition_path=partition_dir,
                        target_uri=uri,
                        rows=table.num_rows,
                        bytes_size=len(payload),
                        written_at=time.time(),
                        bronze_sha256=None,
                        status=SilverStatus.WRITTEN.value,
                    )
                )
        return written

    # ── DRY_RUN simulation ──────────────────────────────────────────────
    def _simulate(self, groups: dict[tuple[str, tuple], list[SilverRecord]]) -> list[str]:
        backend_label = (
            f"{self.backend.name}://"
            f"{getattr(self.backend, 'root', getattr(self.backend, 'bucket', '?'))}"
        )
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
        tables_used = sorted({k[0] for k in groups})
        print(f"  tables           : {', '.join(tables_used)}")
        print(line)

        for (table_name, parts), group_records in groups.items():
            _, table = records_to_table(group_records)
            table = self._sort_table(table)
            partition_dir = _partition_dir(table_name, parts)
            uri = f"{backend_label}/{self._full_key(partition_dir)}/part-{{run-id}}.parquet"
            payload = self._serialise(table)

            print(f"\n▸ table={table_name}  partition: {partition_dir}")
            print(f"    rows               : {table.num_rows}")
            print(f"    estimated size     : {len(payload):,} bytes "
                  f"({len(payload)/1024:.1f} KiB)")
            print(f"    target URI         : {uri}")
            print(f"    schema columns     : {len(SCHEMAS[table_name])}")
            print(f"    sort order         : (event_ts ASC, isin ASC if present)")
            print(f"    sample rows (head 5):")
            head = table.slice(0, 5).to_pydict()
            preview_cols = [
                "event_ts", "exchange", "data_type", "isin", "ticker",
                "trade_price", "trade_size", "bid_price", "ask_price",
                "open", "close", "volume", "trade_flag_canonical",
            ]
            preview_cols = [c for c in preview_cols if c in head]
            for i in range(min(5, table.num_rows)):
                row_repr = ", ".join(f"{c}={head[c][i]}" for c in preview_cols)
                print(f"      [{i}] {row_repr}")

            out.append(uri)

        print(f"\n{line}")
        print(f"DRY_RUN=True  →  no bytes were written to {self.backend.name}.")
        print(f"{line}\n")
        return out


__all__ = ["ParquetWriter"]
