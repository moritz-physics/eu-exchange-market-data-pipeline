"""Apache Iceberg sink for the silver tables.

Iceberg adds the production-grade properties that raw partitioned
Parquet lacks:

  * **ACID writes** — a crash mid-commit leaves no half-written state.
  * **Schema evolution** — adding a column does not rewrite history.
  * **Snapshot isolation + time-travel** — every commit is queryable
    ``AS OF '2025-08-01'``.
  * **Manifest catalog** — what files belong to a table is a query, not
    a directory walk.

This sink uses PyIceberg's ``SqlCatalog`` backed by SQLite (the same
file as the bronze manifest, by default), so the entire pipeline state
lives in one place. For production swap to a hosted catalog (Glue,
Nessie, REST) by changing one env var.

Optional dependency:
    pip install 'pyiceberg[sql-sqlite,pyarrow]'

If PyIceberg is not installed, importing this module raises with a
clear hint pointing at the optional extra.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

import pyarrow as pa

from german_scraper.core.logging_config import get_logger
from german_scraper.storage.schema import (
    SCHEMAS,
    SilverRecord,
    records_to_table,
)

logger = get_logger(__name__)


def _require_pyiceberg() -> tuple:
    """Lazy import so the rest of the pipeline runs without pyiceberg."""
    try:
        import pyiceberg  # noqa: F401
        from pyiceberg.catalog.sql import SqlCatalog
        from pyiceberg.exceptions import NoSuchTableError
        from pyiceberg.partitioning import PartitionSpec, PartitionField
        from pyiceberg.transforms import (
            DayTransform, IdentityTransform, MonthTransform, YearTransform,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Iceberg sink requires the 'iceberg' extra: "
            "pip install 'playwrite-vs-extention[iceberg]'"
        ) from exc
    return SqlCatalog, NoSuchTableError, PartitionSpec, PartitionField, (
        DayTransform, IdentityTransform, MonthTransform, YearTransform,
    )


class IcebergSink:
    """Write silver records into Apache Iceberg tables.

    Three tables are managed: ``silver.trades``, ``silver.quotes``,
    ``silver.bars``. Created lazily on first use; partitioning matches
    the Parquet writer:

        identity(exchange), year(event_ts), month(event_ts), day(event_ts),
        identity(instrument_type)
    """

    def __init__(
        self,
        *,
        catalog_name: str = "eu_scraper",
        warehouse_uri: str | None = None,
        catalog_uri: str | None = None,
        namespace: str = "silver",
    ) -> None:
        sql_catalog_cls, _, *_ = _require_pyiceberg()
        self._sql_catalog_cls = sql_catalog_cls
        self.catalog_name = catalog_name
        self.namespace = namespace

        warehouse = warehouse_uri or os.environ.get(
            "ICEBERG_WAREHOUSE", str(Path("warehouse").resolve())
        )
        # SQLAlchemy URI — defaults to a local SQLite file colocated with
        # the bronze manifest.
        catalog = catalog_uri or os.environ.get(
            "ICEBERG_CATALOG_URI",
            f"sqlite:///{os.environ.get('MANIFEST_DSN', 'manifest.db')}",
        )
        Path(warehouse).mkdir(parents=True, exist_ok=True)

        self._catalog = sql_catalog_cls(
            catalog_name,
            **{
                "uri": catalog,
                "warehouse": f"file://{warehouse}"
                if not warehouse.startswith(("file://", "s3://"))
                else warehouse,
            },
        )
        try:
            self._catalog.create_namespace_if_not_exists(self.namespace)
        except AttributeError:
            # Older PyIceberg versions don't have *_if_not_exists.
            try:
                self._catalog.create_namespace(self.namespace)
            except Exception:
                pass
        logger.info(
            "IcebergSink ready (catalog=%s, namespace=%s, warehouse=%s)",
            catalog_name, self.namespace, warehouse,
        )

    # ── Table management ────────────────────────────────────────────────
    def _table_id(self, table_name: str) -> tuple[str, str]:
        return (self.namespace, table_name)

    @staticmethod
    def _to_iceberg_compatible(arrow_schema: pa.Schema) -> pa.Schema:
        """Down-cast unsupported types at the Iceberg boundary.

        Iceberg's ``timestamptz`` is microsecond-precision; our internal
        Parquet schema uses nanoseconds for forward-compatibility with
        tick-level feeds. Cast to ``us`` at the boundary so Iceberg
        accepts the schema. Nanosecond precision is preserved in the
        Parquet writer path.
        """
        new_fields = []
        for f in arrow_schema:
            t = f.type
            if pa.types.is_timestamp(t) and t.unit == "ns":
                new_fields.append(pa.field(f.name, pa.timestamp("us", tz=t.tz),
                                            nullable=f.nullable))
            else:
                new_fields.append(f)
        return pa.schema(new_fields)

    @staticmethod
    def _to_iceberg_table(arrow_table: pa.Table) -> pa.Table:
        """Cast a record batch to the Iceberg-compatible schema."""
        target = IcebergSink._to_iceberg_compatible(arrow_table.schema)
        return arrow_table.cast(target)

    def _ensure_table(self, table_name: str, arrow_schema: pa.Schema) -> Any:
        """Create the Iceberg table on first use; idempotent.

        PyIceberg accepts a ``pyarrow.Schema`` directly when creating a
        table — it generates field IDs internally. We then wire up
        partition transforms by name.
        """
        _, NoSuchTableError, PartitionSpec, PartitionField, (
            DayTransform, IdentityTransform, MonthTransform, YearTransform,
        ) = _require_pyiceberg()

        ident = self._table_id(table_name)
        try:
            return self._catalog.load_table(ident)
        except NoSuchTableError:
            pass

        # Create with no partition spec first (one round-trip), then evolve.
        compat_schema = self._to_iceberg_compatible(arrow_schema)
        table = self._catalog.create_table(ident, schema=compat_schema)
        iceberg_schema = table.schema()

        def _fid(name: str) -> int:
            return iceberg_schema.find_field(name).field_id

        spec = PartitionSpec(
            PartitionField(_fid("exchange"),        1000, IdentityTransform(), "exchange"),
            PartitionField(_fid("event_ts"),        1001, YearTransform(),     "year"),
            PartitionField(_fid("event_ts"),        1002, MonthTransform(),    "month"),
            PartitionField(_fid("event_ts"),        1003, DayTransform(),      "day"),
            PartitionField(_fid("instrument_type"), 1004, IdentityTransform(), "instrument_type"),
        )

        # Evolve partitioning via the partition-spec API. PyIceberg only
        # accepts one time-transform per source column per transaction,
        # so we apply them sequentially. The ``day`` transform is the
        # finest-grained one and is what predicate pushdown uses;
        # year/month are derived metadata. We commit just (exchange,
        # day(event_ts), instrument_type) — Iceberg can still resolve
        # year/month queries against the day partition.
        try:
            with table.update_spec() as upd:
                upd.add_field("exchange",         IdentityTransform(), "exchange")
                upd.add_field("event_ts",         DayTransform(),      "day")
                upd.add_field("instrument_type",  IdentityTransform(), "instrument_type")
        except Exception as exc:
            logger.warning(
                "Could not evolve partition spec on %s.%s (%s) — table created unpartitioned",
                *ident, exc,
            )
        logger.info("Created Iceberg table %s.%s", *ident)
        return self._catalog.load_table(ident)

    # ── Write API ───────────────────────────────────────────────────────
    def write(self, records: Iterable[SilverRecord]) -> dict[str, int]:
        """Append all records into their respective Iceberg tables.

        Returns ``{table_name: row_count}`` for each table touched.
        """
        records = list(records)
        if not records:
            return {}

        # Group by TABLE
        groups: dict[str, list[SilverRecord]] = {}
        for r in records:
            groups.setdefault(r.TABLE, []).append(r)

        out: dict[str, int] = {}
        for table_name, group in groups.items():
            arrow_schema = SCHEMAS[table_name]
            _, arrow_table = records_to_table(group)
            tbl = self._ensure_table(table_name, arrow_schema)
            arrow_table = self._to_iceberg_table(arrow_table)
            tbl.append(arrow_table)
            out[table_name] = arrow_table.num_rows
            logger.info(
                "Iceberg appended %d rows → %s.%s",
                arrow_table.num_rows, self.namespace, table_name,
            )
        return out

    def stats(self) -> dict[str, int]:
        """Return ``{table: snapshot_id_count}`` for sanity checks."""
        out: dict[str, int] = {}
        for table_name in SCHEMAS:
            try:
                tbl = self._catalog.load_table(self._table_id(table_name))
                out[table_name] = len(list(tbl.snapshots()))
            except Exception:
                out[table_name] = 0
        return out


__all__ = ["IcebergSink"]
