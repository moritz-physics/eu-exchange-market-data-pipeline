# EU Exchange Pre & Post Trade Data Acquisition Pipeline

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-1.59+-2EAD33?logo=playwright&logoColor=white)](https://playwright.dev/)
[![Apache Parquet](https://img.shields.io/badge/Apache%20Parquet-Snappy-50ABF1?logo=apacheparquet&logoColor=white)](https://parquet.apache.org/)
[![PyArrow](https://img.shields.io/badge/PyArrow-24+-blue)](https://arrow.apache.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A high-throughput data acquisition pipeline that scrapes MiFID II pre- and
post-trade publications from a curated set of European trading venues and
delivers them as a unified, partitioned, columnar dataset suitable for
quantitative research, market-microstructure work, and regulatory
back-testing.

---

## Overview

This pipeline is a production-engineering layer over the inherently messy
problem of acquiring EU exchange data: every venue exposes its delayed
data through a different web flow — sometimes a static list of CSVs,
sometimes a request form that emails you a download link, sometimes a
JavaScript-only widget behind reCAPTCHA, sometimes a 2FA-gated portal.
The pipeline normalises all of those into one operational pattern:

1. **Browser automation** with Playwright handles every site-specific
   flow (cookies, consent, login, 2FA prompts, IMAP polling, JS-driven
   downloads).
2. **A unified columnar schema** lifts each venue's payload into a single
   PyArrow record shape — one schema for trades, quotes, OHLCV bars, and
   order-book snapshots across every exchange.
3. **A pluggable storage backend** writes the resulting dataset as
   Snappy-compressed Parquet, partitioned by exchange, date, and
   instrument type, to local disk, S3-compatible object storage, or
   network file systems — chosen at deploy time, not at code time.
4. **A dry-run mode** lets the entire pipeline execute end-to-end against
   real venue data without writing a single byte to disk, which makes
   schema changes, new exchanges, and CI runs safe to iterate on.

This project was built during a student research-assistant position at the
**Faculty of Finance and Banking, Ludwig Maximilian University of Munich
(LMU)** and was used in actual academic research on EU equity, bond, and
energy market microstructure.

---

## Exchange coverage

| Exchange | Country | Pre-trade | Post-trade | Native format | Auth flow |
|---|---|---|---|---|---|
| Börse Berlin | DE | ✅ | ✅ | CSV (RTS-13 style) | none |
| Börse Berlin (cron) | DE | ✅ | ✅ | CSV | none |
| Lang & Schwarz (LSX) | DE | ✅ | — | CSV | cookie consent |
| Börse München (gettex) | DE | ✅ | ✅ | CSV | cookie consent |
| Börsen AG (Düsseldorf / Hamburg / Hannover) | DE | ✅ | ✅ | CSV | iframe unlock |
| Wiener Börse (+ stealth variant) | AT | ✅ | — | ZIP | reCAPTCHA-prone, JS `onClick` |
| Cboe Europe (BXE / CXE / DXE / APA) | EU | — | ✅ | hourly CSV (RTS-13) | OneTrust |
| BME (Bolsas y Mercados Españoles) | ES | — | ✅ | JSON | OneTrust + modal |
| ATHEX / Greek Exchanges | GR | ✅ | ✅ | CSV | cookie consent |
| Bank of Greece (HDAT) | GR | ✅ | ✅ | JSON | none |
| Bucharest Stock Exchange (BVB) | RO | ✅ | ✅ | CSV | popup dismiss + EN switch |
| Luxembourg Stock Exchange (LuxSE) | LU | ✅ | ✅ | request form → emailed link | IMAP polling |
| Bratislava Stock Exchange (BSSE) | SK | ✅ | ✅ | request form → email attachment | IMAP polling |
| ICE (pre-trade `/report/60`) | UK / EU | ✅ | — | CSV per row | login + 2FA |
| ICE (post-trade `/report/61`) | UK / EU | — | ✅ | CSV per row | login + 2FA |
| Deutsche Börse (Frankfurt, Xetra, Tradegate, Eurex) | DE | ✅ | ✅ | `.json.gz` | none (Selenium-based) |

---

## Unified data schema

Every record across every exchange is normalised into the schema below.
Missing fields (e.g. `bid_price` for a post-trade execution) are stored
as nulls; columnar storage compresses them efficiently.

| Column | Type | Required | Description |
|---|---|---|---|
| `event_ts` | `timestamp[ns, UTC]` | ✅ | Event timestamp from the source feed (UTC) |
| `ingest_ts` | `timestamp[ns, UTC]` | ✅ | When this pipeline observed the record (UTC) |
| `exchange` | `string` | ✅ | Internal exchange code (e.g. `BERA`, `CBOE-BXE`, `BOG-HDAT`) |
| `mic` | `string` | | ISO 10383 Market Identifier Code |
| `data_type` | `string` | ✅ | `pre_trade` or `post_trade` |
| `instrument_type` | `string` | | `equity` / `bond` / `etf` / `derivative` / `energy` / `other` |
| `instrument_id` | `string` | | ISIN, ticker, or contract code |
| `instrument_id_type` | `string` | | `ISIN` / `TICKER` / `FIGI` / `INTERNAL` |
| `currency` | `string` | | ISO 4217 |
| `venue_segment` | `string` | | MTF segment / sub-market |
| `bid_price`, `bid_size`, `ask_price`, `ask_size`, `book_level` | `double` / `int32` | | Pre-trade quote / book fields |
| `trade_price`, `trade_size`, `trade_id`, `notional`, `trade_flags` | `double` / `string` | | Post-trade execution fields |
| `open`, `high`, `low`, `close`, `volume` | `double` | | OHLCV bar fields when feed reports bars |
| `source_file` | `string` | | Original payload filename |
| `source_url` | `string` | | Original payload URL |
| `schema_version` | `string` | ✅ | Pinned schema version (`1.0.0`) |

The schema is the single source of truth — see
`german_scraper/storage/schema.py`.

### Partitioning strategy

```
data/
  exchange=<EXCHANGE>/
    year=<YYYY>/
      month=<MM>/
        day=<DD>/
          instrument_type=<TYPE>/
            <data_type>.parquet
```

This Hive-style layout lets downstream queries push exchange, date-range,
and instrument-type predicates down to the file system — DuckDB and Spark
will skip entire partition trees without opening a single Parquet file.
Adding a new exchange does not restructure existing data.

---

## Architecture

```
   ┌─────────────────────────────────────────────────────────────┐
   │  Playwright browser automation (headed in dev, headless     │
   │  in prod) handles 17 venue-specific flows: cookies, login,  │
   │  2FA prompt, IMAP polling, JS onClick triggers, …           │
   └────────────────────────┬────────────────────────────────────┘
                            ↓
   ┌─────────────────────────────────────────────────────────────┐
   │  Per-exchange adapters parse the native payload (CSV /      │
   │  JSON / ZIP / .json.gz) and emit UnifiedRecord instances.   │
   └────────────────────────┬────────────────────────────────────┘
                            ↓
   ┌─────────────────────────────────────────────────────────────┐
   │  ParquetWriter groups records by partition key, validates   │
   │  the schema, serialises with Snappy, and hands bytes to a   │
   │  StorageBackend.                                            │
   └────────────────────────┬────────────────────────────────────┘
                            ↓
   ┌──────────────┬─────────────────┬────────────────────────────┐
   │ LocalBackend │ NFSBackend      │ S3Backend (boto3, lazy)    │
   │  ./data/     │ /mnt/research/  │ s3://bucket/prefix/        │
   └──────────────┴─────────────────┴────────────────────────────┘
```

Operational properties baked in:

* **Async-first** — all scrapers are `async`, run inside a single shared
  Chromium browser context, and yield control between page interactions.
* **Centralised retry** with exponential backoff and jitter
  (`german_scraper.core.retry.with_retry`) around every download click.
* **Manifest-based deduplication** — every payload is keyed by a stable
  label, so re-running the scraper never re-downloads the same file.
* **Per-scraper fault isolation** — one venue failing never aborts the
  rest of the run; failures are logged with full stack traces.
* **Dry-run mode** end-to-end (browser automation + schema + writer)
  without a single byte hitting disk.

---

## Scale

The pipeline is designed for continuous unattended operation on a single
server:

* **Multiple exchanges in parallel** via the shared Chromium context —
  one browser, many pages.
* **Hundreds of files per cron tick** — Berlin alone exposes ~50 new
  pre-trade and ~50 new post-trade CSVs per day. Multiply by 17 venues.
* **Gigabytes of tick-level data per day** when ICE / Cboe hourly feeds
  are active.
* **Snappy-compressed Parquet** typically gives 4–8× compression vs.
  the source CSV / JSON, with read-side throughput limited by network
  rather than CPU.
* **Server-friendly defaults** — `PLAYWRIGHT_HEADLESS=true`,
  `STORAGE_BACKEND=s3` (or `nfs`), `LOG_LEVEL=INFO` — change config, not
  code.

---

## Storage layer in detail

| Concern | Choice | Why |
|---|---|---|
| File format | Apache Parquet | Columnar, splittable, native pandas / polars / DuckDB / Spark support |
| Compression | Snappy | Best decompression-speed-per-byte for analytical workloads (ZSTD compresses better but reads ~3× slower) |
| Row group size | 64K rows | Standard sweet spot for predicate pushdown vs. metadata overhead |
| Partitioning | `exchange / year / month / day / instrument_type` | Aligns with the typical research query (one venue, one date range, one asset class) |
| Backend | Pluggable: `LocalBackend`, `NFSBackend`, `S3Backend` | Same code on a laptop, on the LMU research cluster, and on AWS |

The storage interface is intentionally minimal — `write_bytes(key,
payload)` and `exists(key)` — so adding GCS, Azure Blob, or HDFS support
is one new class.

---

## Dry-run mode

Every component honours a single global flag, `DRY_RUN`, surfaced both as
an environment variable and as `german_scraper.storage.DRY_RUN`. When
`DRY_RUN=true` (the default):

* Scrapers run normally and parse every payload.
* Records are validated against `UNIFIED_SCHEMA` exactly as in production.
* The writer **does not** invoke `StorageBackend.write_bytes`.
* Instead, a structured simulation report is printed for every partition
  the writer would have produced.

Run the bundled demo to see this in action:

```bash
DRY_RUN=true uv run python -m german_scraper.storage.dry_run_demo
```

Sample output (truncated):

```
══════════════════════════════════════════════════════════════════════════════
DRY-RUN SIMULATION  ·  ParquetWriter
══════════════════════════════════════════════════════════════════════════════
  backend          : local://.
  compression      : snappy
  row_group_size   : 65536
  partitions       : 4
  total records    : 5
  schema columns   : 28
══════════════════════════════════════════════════════════════════════════════

▸ Partition: exchange=BERA/year=2025/month=08/day=01/instrument_type=equity/post_trade.parquet
    rows               : 2
    estimated size     : 7,200 bytes (7.0 KiB)
    target URI         : local://./data/exchange=BERA/year=2025/month=08/day=01/instrument_type=equity/post_trade.parquet
    schema (col : dtype):
      - event_ts               timestamp[ns, tz=UTC]
      - ingest_ts              timestamp[ns, tz=UTC]
      - exchange               string
      - data_type              string
      - instrument_id          string
      …
    sample rows (head 5):
      [0] event_ts=2025-08-01 09:30:00+00:00, exchange=BERA, data_type=post_trade, instrument_id=DE0007164600, trade_price=42.78, trade_size=125.0
      [1] event_ts=2025-08-01 09:31:00+00:00, exchange=BERA, data_type=post_trade, instrument_id=DE0007164600, trade_price=42.81, trade_size=80.0
```

To go live, set `DRY_RUN=false` and configure a real backend.

---

## Installation

```bash
# Clone and enter the project
git clone <repo-url> playwrite-vs-extention
cd playwrite-vs-extention

# Use uv (recommended) — installs everything in pyproject.toml
uv sync

# Install the Playwright browser binaries
uv run playwright install chromium
```

Python 3.12+ is required.

---

## Configuration

All runtime configuration is environment-driven so the same image runs
unchanged on a laptop and on a server.

### Browser

| Variable | Default | Notes |
|---|---|---|
| `PLAYWRIGHT_HEADLESS` | `false` | Set `true` on servers |
| `PLAYWRIGHT_SLOWMO_MS` | `0` | Add latency between actions for debugging |

### Logging

| Variable | Default |
|---|---|
| `LOG_LEVEL` | `INFO` |

### Storage

| Variable | Default | Notes |
|---|---|---|
| `DRY_RUN` | `true` | **Set to `false` to actually write data** |
| `STORAGE_BACKEND` | `local` | `local` / `nfs` / `s3` |
| `STORAGE_LOCAL_ROOT` | `.` | Used by `local` and `nfs` backends |
| `STORAGE_S3_BUCKET` | — | Required for `s3` backend |
| `STORAGE_S3_PREFIX` | (empty) | Optional key prefix |
| `STORAGE_S3_ENDPOINT` | — | Optional, e.g. for MinIO |
| `STORAGE_S3_REGION` | — | Optional region override |
| `PARQUET_COMPRESSION` | `snappy` | `snappy` / `zstd` / `gzip` |
| `PARQUET_ROW_GROUP` | `65536` | Rows per row group |

### Per-exchange credentials

| Variable | Used by |
|---|---|
| `ICE_EMAIL`, `ICE_PASSWORD` | ICE pre + post |
| `IMAP_HOST`, `IMAP_USER`, `IMAP_PASS` | LuxSE, Bratislava |
| `LUXSE_FIRST_NAME`, `LUXSE_LAST_NAME`, `LUXSE_RECIPIENT_EMAIL` | LuxSE |
| `BSSE_FIRST_NAME`, `BSSE_LAST_NAME`, `BSSE_RECIPIENT_EMAIL` | Bratislava |

ICE additionally prompts for a 2FA code on stdin at the start of every run.

### Selecting exchanges

Edit the `SCRAPERS` list in `german_scraper/cli.py`. Each entry maps to
one scraper class — the file's existing comments document which venues
are stable and which are still flaky.

---

## Running the scraper

```bash
# Dry run (default — recommended for first run)
uv run python -m german_scraper.cli

# Production run, writing to local disk
DRY_RUN=false STORAGE_BACKEND=local STORAGE_LOCAL_ROOT=/var/data \
  PLAYWRIGHT_HEADLESS=true \
  uv run python -m german_scraper.cli

# Production run, writing to S3
DRY_RUN=false STORAGE_BACKEND=s3 STORAGE_S3_BUCKET=lmu-finance-research \
  STORAGE_S3_PREFIX=eu-exchanges/v1 \
  PLAYWRIGHT_HEADLESS=true \
  uv run python -m german_scraper.cli
```

---

## Deployment note

The system is intended to live on a long-running server with the dataset
written to network storage (NFS / S3), **not** the server's local disk.
At LMU the production deployment writes to a research-cluster NFS mount;
on AWS it writes to S3. Switching between the two is one environment
variable.

The scraper itself is single-binary — no message queue, no scheduler, no
database — and is meant to be invoked under cron, systemd timers, or a
Kubernetes `CronJob`. The `Berlin` and `BerlinCron` variants demonstrate
how to size a per-tick batch for periodic execution.

---

## Research context

Built during a student research-assistant position at the
**Faculty of Finance and Banking, Ludwig Maximilian University of Munich
(LMU)**. Used in faculty research on EU equity, bond, and energy market
microstructure — specifically work touching MiFID II RTS-13 delayed-data
publications, post-trade transparency analysis, and venue-by-venue
liquidity comparison.

---

## License

MIT.
