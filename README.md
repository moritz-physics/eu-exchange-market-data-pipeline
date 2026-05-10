# EU Exchange Pre & Post Trade Data Acquisition Pipeline

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-1.59+-2EAD33?logo=playwright&logoColor=white)](https://playwright.dev/)
[![Apache Iceberg](https://img.shields.io/badge/Apache%20Iceberg-ACID-blue?logo=apache&logoColor=white)](https://iceberg.apache.org/)
[![Apache Parquet](https://img.shields.io/badge/Apache%20Parquet-Snappy-50ABF1?logo=apacheparquet&logoColor=white)](https://parquet.apache.org/)
[![Tests](https://img.shields.io/badge/tests-30%2F30-brightgreen.svg)](tests_python)
[![mypy](https://img.shields.io/badge/mypy-strict-2A6DB2.svg)](https://mypy.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A high-throughput data acquisition pipeline that scrapes MiFID II pre-
and post-trade publications from a curated set of European trading
venues and delivers them as a unified, ACID-managed, partitioned,
columnar dataset suitable for quantitative research,
market-microstructure work, and regulatory back-testing.

---

## Overview

Every venue exposes its delayed data through a different web flow —
sometimes a static list of CSVs, sometimes a request form that emails
you a download link, sometimes a JS-only widget behind reCAPTCHA,
sometimes a 2FA-gated portal. This pipeline normalises all of them
into one operational pattern, then layers a proper data engine on top:

1. **Browser automation** with Playwright handles every site-specific
   flow (cookies, consent, login, TOTP, IMAP, JS-driven downloads).
   For plain `<a href>` links, the **HTTP fast path** streams files
   over `aiohttp` with cookies copied from the browser context — about
   10× faster than triggering Playwright's download mechanism.
2. **Bronze → silver medallion architecture.** Scrapers land raw bytes
   in a *bronze* layer (immutable). A separate `ingest` job turns
   bronze into typed, normalised silver records. A parser bug means
   `ingest` re-runs against the same bronze — no need to refetch from
   venues.
3. **Three narrow PyArrow schemas** — `trades`, `quotes`, `bars` — so
   files compress well, stats prune well, and queries read naturally.
   Each record carries `seq`, `event_ts`, `publication_ts`,
   `received_ts`, `ingest_ts`, plus first-class `isin` / `ticker` /
   `figi` columns and a canonical `trade_flag_canonical` enum.
4. **Apache Iceberg sink** for ACID writes, snapshot isolation,
   time-travel (`AS OF`) queries, and transparent schema evolution.
   Parquet-only sink remains as an alternative for environments
   without the Iceberg catalog.
5. **SQLite manifest** acts as the bronze + silver catalog and the DLQ.
   Operational questions ("how many BERA files yesterday?", "what's
   still pending?") become single-line `sqlite3` queries.
6. **Concurrent scraping** with bounded semaphore and one Playwright
   *context* per scraper so cookies don't leak between venues.
7. **Pluggable storage backend** (Local / NFS / S3 with atomic
   staging-then-copy commits) chosen at deploy time, not code time.
8. **JSON logging** when stdout isn't a TTY, **Prometheus-style
   counters** for ops, and **DQ gates** that fail loud when a venue
   silently degrades.
9. **Dry-run mode** end-to-end (browser automation + schema + writer)
   without a single byte hitting disk.

Built during a student research-assistant position at the
**Faculty of Finance and Banking, Ludwig Maximilian University of Munich
(LMU)** and used in actual academic research on EU equity, bond, and
energy market microstructure.

---

## Exchange coverage

| Exchange | Country | Pre-trade | Post-trade | Native format | Auth flow | HTTP fast path |
|---|---|---|---|---|---|---|
| Börse Berlin | DE | ✅ | ✅ | CSV (RTS-13) | none | ✅ |
| Börse Berlin (cron) | DE | ✅ | ✅ | CSV | none | ✅ |
| Lang & Schwarz (LSX) | DE | ✅ | — | CSV | cookie consent | — (button) |
| Börse München (gettex) | DE | ✅ | ✅ | CSV | cookie consent | — (popup) |
| Börsen AG | DE | ✅ | ✅ | CSV | iframe unlock | — (iframe) |
| Wiener Börse (+ stealth) | AT | ✅ | — | ZIP | reCAPTCHA / JS `onClick` | — (JS) |
| Cboe Europe (BXE/CXE/DXE/APA) | EU | — | ✅ | hourly CSV (RTS-13) | OneTrust | ✅ |
| BME (Bolsas y Mercados Españoles) | ES | — | ✅ | JSON | OneTrust | — (Alt-click) |
| ATHEX | GR | ✅ | ✅ | CSV | cookie consent | ✅ |
| Bank of Greece (HDAT) | GR | ✅ | ✅ | JSON | none | ✅ |
| Bucharest Stock Exchange | RO | ✅ | ✅ | CSV | popups | — (button) |
| Luxembourg Stock Exchange | LU | ✅ | ✅ | request form → emailed link | IMAP IDLE | n/a |
| Bratislava Stock Exchange | SK | ✅ | ✅ | request form → email attachment | IMAP polling | n/a |
| ICE pre-trade (`/report/60`) | UK / EU | ✅ | — | CSV per row | login + TOTP | — (button) |
| ICE post-trade (`/report/61`) | UK / EU | — | ✅ | CSV per row | login + TOTP | — (button) |
| Deutsche Börse (Frankfurt/Xetra/Tradegate/Eurex) | DE | ✅ | ✅ | `.json.gz` | none (Selenium) | n/a |

---

## Data architecture

### Medallion layers

```
   venues  ───► [ Playwright + HTTP fast path ] ──► bronze (raw bytes)
                                                       │
                                       SQLite manifest │ status, sha256
                                                       ▼
                       [ ingest job ] ───── adapters per exchange
                                       │   instrument-master enrich
                                       ▼
                                   silver (Parquet · Iceberg)
                                       │
                                       ▼
                       pandas │ DuckDB │ Spark │ Trino
```

* **Bronze** is the immutable archive of every raw payload, written
  exactly once, fingerprinted by SHA-256.
* **Silver** is the typed, queryable dataset. Regenerable from bronze
  at any time. ACID via Apache Iceberg, or plain partitioned Parquet
  if Iceberg isn't desired.

### Three narrow schemas

| Table | Used for | Example columns |
|---|---|---|
| `trades` | post-trade executions, trade reports | `trade_price`, `trade_size`, `trade_id`, `notional`, `side`, `trade_flag_canonical`, `trade_flags_raw` |
| `quotes` | pre-trade quotes / order-book snapshots | `bid_price`, `bid_size`, `ask_price`, `ask_size`, `book_level`, `snapshot` |
| `bars` | OHLCV bars (Bank of Greece HDAT etc.) | `bar_interval`, `open`, `high`, `low`, `close`, `volume`, `vwap`, `trades_count` |

Common columns on every table: `event_ts`, `publication_ts`,
`received_ts`, `ingest_ts`, `seq`, `exchange`, `mic`, `data_type`,
`isin`, `ticker`, `figi`, `venue_instrument_id`, `instrument_type`,
`currency`, `venue_segment`, `source_file`, `source_url`,
`source_msg_hash`, `schema_version`.

Identifiers are split into separate columns (no single-column +
type-tag), so research joins are trivial. Trade flags are mapped from
venue-specific RTS-1/RTS-2 codes (`LRGS`, `BENC`, `NPFT`, …) onto a
canonical enum: `large_in_scale`, `benchmark`, `negotiated`, `dark`,
`offbook`, `agency_cross`, `systematic_internaliser`, `late_publication`,
`cancellation`, `amendment`, `normal`, `unknown`. The raw flag is
preserved verbatim in `trade_flags_raw`.

### Partitioning

Parquet sink:
```
data/{table}/exchange={EXCHANGE}/year={YYYY}/month={MM}/day={DD}/instrument_type={t}/part-{ts}.parquet
```

Iceberg sink: `(identity(exchange), day(event_ts), identity(instrument_type))` —
day-partitioned, with year/month derivable from the day partition.

Within each partition rows are sorted by `(event_ts, isin)` so Parquet's
per-row-group min/max stats prune efficiently for any time-range or
instrument query.

---

## Operational properties

* **Async-first** — every scraper is an async coroutine, run in
  parallel inside a single shared Chromium browser bounded by a
  `Semaphore`. One Playwright `BrowserContext` per scraper isolates
  cookies between venues.
* **HTTP fast path** for plain-href venues skips the browser's
  download mechanism entirely; cookies are copied from the active
  Playwright context into an `aiohttp.ClientSession`.
* **TOTP-driven 2FA** for ICE — when `ICE_TOTP_SECRET` is set the
  scraper generates the code via `pyotp` and never blocks on stdin.
* **IMAP IDLE** for LuxSE / Bratislava — push notifications when the
  server supports them, polling fallback when it doesn't.
* **Centralised retry** with exponential backoff and jitter
  (`with_retry`) wraps every download call.
* **Atomic S3 writes** — staging key + `CopyObject` + `DeleteObject`
  so a crash mid-PUT never leaves a half-written object the next run
  thinks is complete.
* **DQ gates** — per-venue minimum daily volumes and maximum failure
  rates. The `eu-scraper dq` command exits non-zero on violation,
  ready to wire into Prometheus / k8s alertmanager.
* **Per-scraper fault isolation** — one venue failing never aborts
  the rest of the run.
* **Dry-run mode** — schema validation, partitioning and serialisation
  all run identically; the writer just doesn't touch the backend.

---

## Quickstart

```bash
# Clone and enter the project
git clone <repo-url> playwrite-vs-extention
cd playwrite-vs-extention

# Use uv (recommended) — installs everything in pyproject.toml
uv sync

# Install the Playwright browser binaries (one-time)
uv run playwright install chromium

# Optional: install the Iceberg sink
uv sync --extra iceberg --prerelease=allow
```

Python 3.12+ required.

### CLI

```bash
$ python -m german_scraper.cli --help

Usage: python -m german_scraper.cli [OPTIONS] COMMAND [ARGS]...

  EU exchange pre & post-trade data acquisition pipeline.

  scrape          Run scrapers concurrently with cookie-isolated contexts.
  ingest          Process pending bronze payloads into the silver Parquet dataset.
  dq              Evaluate data-quality rules. Exits non-zero on any failure.
  manifest-stats  Print bronze/silver counts by status from the SQLite manifest.
  metrics         Render the in-process metrics registry in Prometheus format.
  demo            Run the storage-layer dry-run demo (synthetic records, no I/O).
```

Day-to-day:

```bash
# Dry-run the full pipeline (no network, no disk writes)
python -m german_scraper.cli demo

# Scrape Berlin + CBOE in production mode (writes to bronze)
DRY_RUN=false STORAGE_BACKEND=s3 STORAGE_S3_BUCKET=lmu-finance-research \
  PLAYWRIGHT_HEADLESS=true \
  python -m german_scraper.cli scrape --exchanges berlin,cboe --no-debug

# Convert pending bronze rows to silver Parquet (or Iceberg)
python -m german_scraper.cli ingest

# Verify data-quality gates after a run
python -m german_scraper.cli dq --window-hours 24
```

---

## Configuration

All runtime configuration is environment-driven so the same image runs
unchanged on a laptop and a server.

### Browser

| Variable | Default | Notes |
|---|---|---|
| `PLAYWRIGHT_HEADLESS` | `false` | Set `true` on servers |
| `PLAYWRIGHT_SLOWMO_MS` | `0` | Add per-action latency for debugging |
| `CONCURRENCY` | `4` | Max parallel scrapers in `scrape` |

### Logging & metrics

| Variable | Default | Notes |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Standard Python log level |
| `LOG_FORMAT` | `auto` | `text` for humans, `json` for k8s/ELK; `auto` picks JSON when stdout isn't a TTY |

### Storage

| Variable | Default | Notes |
|---|---|---|
| `DRY_RUN` | `true` | Set `false` to actually write |
| `STORAGE_BACKEND` | `local` | `local` / `nfs` / `s3` |
| `STORAGE_LOCAL_ROOT` | `.` | Used by `local` and `nfs` backends |
| `STORAGE_S3_BUCKET` | — | Required for `s3` backend |
| `STORAGE_S3_PREFIX` | (empty) | Optional key prefix |
| `STORAGE_S3_ENDPOINT` | — | Optional, e.g. for MinIO |
| `STORAGE_S3_REGION` | — | Optional region override |
| `PARQUET_COMPRESSION` | `snappy` | `snappy` / `zstd` / `gzip` |
| `PARQUET_ROW_GROUP` | `65536` | Rows per row group |
| `MANIFEST_DSN` | `manifest.db` | SQLite path for bronze/silver manifest |
| `ICEBERG_WAREHOUSE` | `./warehouse` | Iceberg warehouse root (file:// or s3://) |
| `ICEBERG_CATALOG_URI` | `sqlite:///{MANIFEST_DSN}` | SQLAlchemy URI for the catalog |
| `INSTRUMENT_MASTER_PATH` | — | CSV with `isin,ticker,figi,asset_class,country,currency` |

### Per-venue credentials

| Variable | Used by |
|---|---|
| `ICE_EMAIL`, `ICE_PASSWORD` | ICE pre + post |
| `ICE_TOTP_SECRET` | ICE TOTP (skip the stdin prompt) |
| `IMAP_HOST`, `IMAP_USER`, `IMAP_PASS` | LuxSE, Bratislava |
| `LUXSE_FIRST_NAME`, `LUXSE_LAST_NAME`, `LUXSE_RECIPIENT_EMAIL` | LuxSE |
| `BSSE_FIRST_NAME`, `BSSE_LAST_NAME`, `BSSE_RECIPIENT_EMAIL` | Bratislava |

---

## Deployment

A multi-stage `Dockerfile` ships with the repo. It builds on
`mcr.microsoft.com/playwright/python` so Chromium and system fonts
come pre-installed. The image runs as a non-root user, defaults to
JSON logs, and writes manifest + warehouse to `/var/lib/eu-scraper`.

```bash
docker build -t eu-scraper:latest .
# With Iceberg sink:
docker build --build-arg ICEBERG=1 -t eu-scraper:latest .
```

`deploy/k8s-cronjob.yaml` is a working example with three CronJobs:

* `eu-scraper-scrape`  – every 30 min, scrape into bronze
* `eu-scraper-ingest`  – every 30 min (offset), bronze → silver
* `eu-scraper-dq`      – daily at 06:00 UTC, exits non-zero on alert

A `PersistentVolumeClaim` is mounted at `/var/lib/eu-scraper` for the
SQLite manifest and Iceberg warehouse; secrets come from a `Secret`
named `eu-scraper-secrets`.

---

## Tests

```bash
uv run pytest                           # 30/30 currently
uv run mypy --package german_scraper.storage  # strict on storage/
```

Tests cover: schema stability (bumping `SCHEMA_VERSION` is enforced),
adapter golden inputs, manifest lifecycle (downloaded → ingested →
failed), writer round-trip, DRY_RUN simulation, ingest end-to-end,
DLQ behaviour on writer crash, metrics rendering, DQ gate evaluation,
Iceberg snapshot isolation.

The HTTP fast path is verified against a local HTTP server with
canned HTML — no live venue traffic in CI.

---

## Research context

Built during a student research-assistant position at the
**Faculty of Finance and Banking, Ludwig Maximilian University of Munich
(LMU)**. Used in faculty research on EU equity, bond, and energy
market microstructure — specifically work touching MiFID II RTS-13
delayed-data publications, post-trade transparency analysis, and
venue-by-venue liquidity comparison.

---

## License

MIT.
