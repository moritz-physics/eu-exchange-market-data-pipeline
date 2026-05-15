# Improvement Suggestions

Recommendations identified during the quality audit but **not implemented**.
Each item is tagged `effort` (low/medium/high) and `impact` (low/medium/high).

---

## Performance improvements

- **Stream HTTP downloads to disk instead of buffering in memory.**
  `core/http_downloader.http_download` does `payload = await resp.read()`,
  loading the whole file into RAM before the pipeline writes it. For Berlin
  (50 files/run) and Cboe (~55 files/run) this is fine, but a multi-MB BVB
  Excel held fully in memory per concurrent scraper adds up. Stream via
  `resp.content.iter_chunked()` to a temp file. — *effort: medium, impact: medium*

- **Parallelise per-file HTTP downloads within a scraper.** Berlin/Cboe/ATHEX
  download anchors sequentially in a `for` loop. A bounded `asyncio.gather`
  (e.g. 4–6 in flight) would cut wall-clock time several-fold while staying
  polite. — *effort: medium, impact: high*

- **Reuse a single `aiohttp.ClientSession` per scraper run.** `http_download`
  opens and tears down a new `ClientSession` for every file, discarding the
  connection pool and re-copying the cookie jar each time. Pass a shared
  session through. — *effort: medium, impact: medium*

- **Skip the browser entirely for venues that never needed it.** Bank of
  Greece, Cboe and ATHEX use Playwright only to read an anchor list / accept
  cookies. Where the anchor URLs are stable, a cached URL template would let
  routine runs bypass Chromium launch (~1–2 s + ~300 MB RSS per context).
  — *effort: high, impact: medium*

- **Raise `ParquetWriter.row_group_size` awareness.** Default 64 Ki rows is
  reasonable, but tiny ingest batches still emit one row group; a compaction
  job (already mentioned in code comments) should be scheduled. — *effort: medium, impact: medium*

---

## Reliability improvements

- **Add a global rate limiter / token bucket per host.** `throttle.random_delay`
  gives a per-call jittered sleep but there is no shared limiter — under
  `concurrency=4` two scrapers can still hammer related endpoints. A
  per-domain token bucket would make politeness a guarantee, not a hope.
  — *effort: medium, impact: high*

- **Backoff is retry-only, not circuit-breaking.** `core/retry.with_retry`
  retries 3× then gives up. A repeatedly-failing venue still gets hit every
  run. Add a circuit breaker that short-circuits a venue after N consecutive
  failed runs and reports it. — *effort: medium, impact: medium*

- **Session/cookie persistence.** Every run starts a cold `BrowserContext`,
  so consent banners and (for ICE) logins are re-done each time. Persisting
  `storage_state` per venue would cut steps and reduce bot-detection
  surface. — *effort: medium, impact: medium*

- **Proxy rotation for bot-protected venues.** Bank of Greece returned
  HTTP 403 (Akamai edge) from this environment, and Wiener Börse already
  needs a stealth variant. A residential/EU proxy pool with rotation would
  materially raise success rates for geo- or bot-gated sites.
  — *effort: high, impact: high*

- **Treat `wait_for_attachments` IMAP timeouts as soft failures with resume.**
  LuxSE/Bratislava block up to 5–10 min on email; if the process dies the
  request is lost. Persist "awaiting email since T" state so a later run can
  pick up the already-sent link. — *effort: high, impact: medium*

- **Tighten `except Exception: pass` blocks.** Several consent helpers swallow
  every exception. Narrow to `TimeoutError` / `PlaywrightError` so genuine
  bugs (e.g. a renamed selector) surface instead of being silently ignored.
  — *effort: low, impact: medium*

---

## Storage improvements

- **Wire `bronze_sha256` provenance into silver rows.** `ParquetWriter.write`
  records `bronze_sha256=None` in the manifest's silver table even though
  ingest knows the originating bronze row. Threading it through enables
  exact bronze→silver lineage queries. — *effort: low, impact: medium*

- **Make the partition file name fully deterministic.** `part-{run_ms}-{abs(hash(parts))%100000}`
  uses Python's salted `hash()`, so the suffix is not reproducible across
  processes. Use a stable hash (`hashlib`) of the partition key.
  — *effort: low, impact: low*

- **Add a compaction / retention job.** The Parquet layout is one file per
  run per partition (by design), and `SilverStatus.COMPACTED`/`EXPIRED`
  exist in the enum but nothing produces them. A scheduled compactor would
  keep small-file counts bounded. — *effort: medium, impact: high*

- **Verify writes on S3.** `S3Backend.write_bytes` does staging→copy→delete
  but never confirms the final object. A `head_object` check (or checksum
  compare) post-copy would close the gap. — *effort: low, impact: medium*

- **Bronze payloads only ever live on local disk.** `ingest._read_bytes`
  raises `NotImplementedError` for `s3://`. If bronze ever moves off the
  scraper host the ingest job breaks; implement the S3 read path.
  — *effort: medium, impact: medium*

---

## Architecture improvements

> **✅ All items in this section were implemented** (see `STATUS.md` →
> "Architecture refactor"). Retained here as a record of the work done.

- **✅ Consolidated on Python; retired the TypeScript `tests/*.spec.js`
  prototypes.** The 13 `.spec.js` files (first-generation scrapers, not
  tests) and the TypeScript harness (`playwright.config.ts`,
  `package.json`, `package-lock.json`, `tests-examples/`) were moved to
  `legacy/playwright-prototypes/`. Borsa Bulgaria — the only venue not
  already in the Python pipeline — was ported to
  `german_scraper/exchanges/bulgaria.py` (`BorsaBulgaria(Exchange)`).

- **✅ Folded the Selenium Deutsche Börse scraper into `german_scraper/`.**
  Re-implemented as `german_scraper/exchanges/deutsche_boerse.py`
  (`DeutscheBoerse(Exchange)`) — a Playwright subclass that gains the
  manifest dedupe, retries, metrics and DQ gates of the rest of the
  pipeline. The old Selenium + Firefox version moved to
  `legacy/deutsche-boerse-selenium/`.

- **✅ Introduced a real config file.** `config.json` (loaded by
  `german_scraper/settings.py`) is now the single source for
  `default_enabled`, `concurrency`, per-venue `pacing`, `dq_rules` and
  exchange `urls`. Every accessor falls back to a built-in default, so a
  missing or partial config never breaks the pipeline.

- **✅ Removed the bogus `asyncio` runtime dependency** via
  `uv remove asyncio`; `pyproject.toml` and `uv.lock` are now consistent
  (`uv lock --check` passes).

- **✅ Reconciled `requirements.txt`.** Moved to
  `legacy/deutsche-boerse-selenium/requirements.txt` (scoped to the legacy
  scraper); the maintained pipeline uses `pyproject.toml` exclusively.

- **✅ Deleted the placeholder `main.py`.**

---

## New features worth adding

- **Scheduling.** A `deploy/k8s-cronjob.yaml` exists; add per-venue cron
  cadences (hourly for Cboe, daily for HDAT, etc.) and document them.
  — *effort: low, impact: medium*

- **Monitoring & alerting.** `core/metrics.py` emits Prometheus-format
  counters but nothing scrapes them. Expose a `/metrics` endpoint or push
  to a gateway, and page on the existing DQ-gate failures. — *effort: medium, impact: high*

- **Data validation beyond row counts.** `core/dq.py` checks file counts and
  failure rate. Add value-level checks: non-negative prices/sizes, ISIN
  checksum validity, `event_ts` within a plausible window, monotonic `seq`.
  — *effort: medium, impact: high*

- **End-to-end smoke test in CI.** *Partially done* — the GitHub workflow
  now runs `uv run pytest tests_python/` instead of the live `.spec.js`
  scrapers (`.github/workflows/ci.yml`). Still worth adding: a Playwright
  smoke test against a static local fixture page so the browser-automation
  path is also exercised in CI. — *effort: medium, impact: medium*

- **Schema-evolution path.** `SCHEMA_VERSION` is pinned and a test enforces
  bumping it, but there is no documented migration story for old Parquet
  files when the schema changes. The Iceberg sink handles this; document it
  or make Iceberg the default. — *effort: medium, impact: medium*
