"""Bronze → silver ingestion job.

Walks the manifest's ``bronze`` table looking for rows in ``DOWNLOADED``
state, dispatches each payload through its registered adapter, applies
optional instrument-master enrichment, and writes the resulting silver
records via :class:`ParquetWriter`. On success the bronze row is
flipped to ``INGESTED``; on failure it goes to ``FAILED`` (DLQ) with
the error message.

Why decouple scrape from parse:
    A parser bug should not require re-fetching data from venues. Bronze
    is immutable; silver is regenerable. This is the standard
    medallion-architecture split (Databricks / Delta Lake).

Adding a new exchange:
    Add an entry to :data:`ADAPTER_REGISTRY` keyed by the exchange code
    used in the ``bronze.exchange`` column.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional

from german_scraper.core.logging_config import get_logger
from german_scraper.core.manifest_db import (
    BronzeRecord,
    DEFAULT_MANIFEST_PATH,
    Manifest,
)
from german_scraper.core.metrics import METRICS
from german_scraper.storage.adapters import (
    adapt_bme_posttrade_json,
    adapt_bog_hdat_json,
    adapt_rts13_csv,
)
from german_scraper.storage.config import StorageConfig
from german_scraper.storage.instruments import InstrumentMaster
from german_scraper.storage.parquet_writer import ParquetWriter
from german_scraper.storage.schema import DataType, SilverRecord

logger = get_logger(__name__)


# Adapter signature: takes raw bytes plus context kwargs, yields silver records.
AdapterFn = Callable[..., Iterator[SilverRecord]]


@dataclass(frozen=True)
class AdapterSpec:
    """Binding between a bronze record and the parser that handles it."""

    fn: AdapterFn
    # Static kwargs forwarded to the adapter on every call.
    kwargs: dict[str, object]


def _rts13(exchange: str, mic: Optional[str], data_type: DataType) -> AdapterSpec:
    return AdapterSpec(
        fn=adapt_rts13_csv,
        kwargs={"exchange": exchange, "mic": mic, "data_type": data_type},
    )


# Registry keyed by ``bronze.exchange``. Add entries here when a new
# venue's adapter is ready; bronze rows whose exchange is unmapped are
# left in DOWNLOADED state and reported but not failed (so adding an
# adapter later is non-destructive).
ADAPTER_REGISTRY: dict[str, AdapterSpec] = {
    "berlin/pretrade":  _rts13("BERA", "BERA", DataType.PRE_TRADE),
    "berlin/posttrade": _rts13("BERA", "BERA", DataType.POST_TRADE),
    "berlin":           _rts13("BERA", "BERA", DataType.POST_TRADE),
    "athex":            _rts13("ATHEX", "ASEX", DataType.POST_TRADE),
    "cboe":             _rts13("CBOE", None,    DataType.POST_TRADE),
    "bme":              AdapterSpec(adapt_bme_posttrade_json, {}),
    "bme/post-trade":   AdapterSpec(adapt_bme_posttrade_json, {}),
    "bank-of-greece":          AdapterSpec(adapt_bog_hdat_json, {"data_type": DataType.POST_TRADE}),
    "bank-of-greece/Pre-Trade":  AdapterSpec(adapt_bog_hdat_json, {"data_type": DataType.PRE_TRADE}),
    "bank-of-greece/Post-Trade": AdapterSpec(adapt_bog_hdat_json, {"data_type": DataType.POST_TRADE}),
}


def _resolve_adapter(exchange: str) -> Optional[AdapterSpec]:
    """Match by exact key, then by exchange root prefix (e.g. ``berlin``)."""
    if exchange in ADAPTER_REGISTRY:
        return ADAPTER_REGISTRY[exchange]
    root = exchange.split("/", 1)[0]
    return ADAPTER_REGISTRY.get(root)


def _read_bytes(uri: str) -> bytes:
    """Read a payload from the URI recorded on a bronze row.

    Currently supports local paths (and ``label-only://`` no-ops). S3
    pulls would slot in here when the scraper writes bronze to S3.
    """
    if uri.startswith("label-only://") or uri.startswith("legacy://"):
        return b""
    if uri.startswith("file://"):
        uri = uri[len("file://"):]
    if uri.startswith("s3://"):
        raise NotImplementedError("S3 bronze read not implemented yet")
    return Path(uri).read_bytes()


def _records_for(bronze: BronzeRecord, payload: bytes) -> list[SilverRecord]:
    spec = _resolve_adapter(bronze.exchange)
    if spec is None:
        return []
    records = list(
        spec.fn(payload, source_file=bronze.label, **spec.kwargs)
    )
    # Tag every record with the bronze sha for back-traceability.
    for r in records:
        r.source_msg_hash = r.source_msg_hash or bronze.sha256
    return records


@dataclass
class IngestStats:
    """Summary of one ingest pass."""

    seen: int = 0
    parsed_rows: int = 0
    files_ok: int = 0
    files_failed: int = 0
    files_skipped_no_adapter: int = 0


def run_ingest(
    *,
    manifest: Manifest | None = None,
    writer: ParquetWriter | None = None,
    exchange: Optional[str] = None,
    limit: int = 1000,
    instrument_master: InstrumentMaster | None = None,
) -> IngestStats:
    """Process pending bronze rows into silver.

    Args:
        manifest: SQLite manifest. Defaults to the env-resolved one.
        writer:   Parquet sink. Defaults to env-resolved + writes manifest entries.
        exchange: Restrict to this exchange (substring match on the
            bronze ``exchange`` column).
        limit:    Maximum bronze rows to process per call.
        instrument_master: Optional reference-data joiner. Defaults to
            loading from ``INSTRUMENT_MASTER_PATH`` env var if set.
    """
    manifest = manifest or Manifest(DEFAULT_MANIFEST_PATH)
    if writer is None:
        cfg = StorageConfig.from_env()
        writer = ParquetWriter(
            backend=cfg.backend,
            compression=cfg.compression,
            row_group_size=cfg.row_group_size,
            dry_run=cfg.dry_run,
            manifest=manifest,
        )

    if instrument_master is None:
        master_path = os.environ.get("INSTRUMENT_MASTER_PATH")
        instrument_master = (
            InstrumentMaster.from_csv(master_path) if master_path else InstrumentMaster()
        )

    pending = manifest.list_pending_bronze(exchange=exchange, limit=limit)
    stats = IngestStats(seen=len(pending))
    logger.info("Ingest pass: %d pending bronze rows", stats.seen)

    batch: list[SilverRecord] = []
    bronze_in_batch: list[BronzeRecord] = []

    for bronze in pending:
        spec = _resolve_adapter(bronze.exchange)
        if spec is None:
            stats.files_skipped_no_adapter += 1
            logger.debug("No adapter for exchange=%s; skipping %s",
                         bronze.exchange, bronze.label)
            continue

        try:
            payload = _read_bytes(bronze.source_uri)
            if not payload:
                manifest.mark_bronze_ingested(bronze.sha256)
                stats.files_ok += 1
                continue
            records = _records_for(bronze, payload)
            if not records:
                logger.warning("Adapter for %s returned no records from %s",
                               bronze.exchange, bronze.label)
                manifest.mark_bronze_ingested(bronze.sha256)
                stats.files_ok += 1
                continue
            batch.extend(records)
            bronze_in_batch.append(bronze)
            stats.parsed_rows += len(records)
        except Exception as exc:  # adapter-level failure → DLQ
            logger.exception("Ingest failed for %s/%s: %s",
                             bronze.exchange, bronze.label, exc)
            manifest.mark_bronze_failed(bronze.sha256, repr(exc))
            stats.files_failed += 1

    # Reference-data join before write so silver rows already have
    # ticker / FIGI / asset class populated.
    if batch:
        n_enriched = instrument_master.enrich(batch)
        if n_enriched:
            logger.info("Enriched %d/%d records via instrument master",
                        n_enriched, len(batch))

    # One write call per pass amortises the dry-run report and groups files.
    if batch:
        try:
            writer.write(batch)
        except Exception as exc:
            # Writer-level failure → roll the whole batch into the DLQ.
            logger.exception("Writer failed for batch: %s", exc)
            for bronze in bronze_in_batch:
                manifest.mark_bronze_failed(bronze.sha256, f"writer: {exc!r}")
                stats.files_failed += 1
        else:
            for bronze in bronze_in_batch:
                manifest.mark_bronze_ingested(bronze.sha256)
                stats.files_ok += 1
                METRICS.inc(
                    "ingest_files_total",
                    description="Bronze files successfully ingested to silver",
                    exchange=bronze.exchange.split("/", 1)[0],
                )

    METRICS.inc(
        "ingest_rows_total", by=float(stats.parsed_rows),
        description="Silver rows produced by ingest",
    )

    logger.info(
        "Ingest pass complete: ok=%d failed=%d no_adapter=%d rows=%d",
        stats.files_ok, stats.files_failed,
        stats.files_skipped_no_adapter, stats.parsed_rows,
    )
    return stats


def main() -> None:
    """Entrypoint: ``python -m german_scraper.storage.ingest``."""
    import argparse
    p = argparse.ArgumentParser(description="Run the bronze→silver ingest pass")
    p.add_argument("--exchange", help="Restrict to this exchange root")
    p.add_argument("--limit", type=int, default=1000)
    args = p.parse_args()
    run_ingest(exchange=args.exchange, limit=args.limit)


if __name__ == "__main__":
    main()
