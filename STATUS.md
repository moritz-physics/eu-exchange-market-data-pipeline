# Project Status — Quality Audit

**Audit date:** 2026-05-15
**Scope:** Playwright-based EU exchange market-data scraping pipeline.

> **Update — architecture refactor completed.** After the audit below,
> all six "Architecture improvements" from `SUGGESTIONS.md` were
> implemented. The pipeline is now **Python-only** in the active tree;
> the TypeScript prototypes and the Selenium scraper were archived under
> `legacy/`. See **§8** for details. Sections §1–§7 are the original
> audit findings and are left as a record.

---

## 1. Python vs TypeScript architecture

The repository contains **three** scraper code bodies. Only one is the
maintained product.

| Code body | Language | Role |
|---|---|---|
| `german_scraper/` | **Python** (Playwright async) | **Primary** — the maintained pipeline. 16 exchange scrapers + medallion storage (bronze→silver), SQLite manifest, Parquet/Iceberg sinks, Typer CLI, metrics, DQ gates. |
| `tests/*.spec.js` | **TypeScript/JS** (Playwright Test) | **Legacy / secondary** — 13 first-generation scrapers written as `.spec.js` "tests". Not unit tests; they perform live downloads. Superseded by the Python scrapers. |
| `DeutscheBoerse/` | **Python** (Selenium + Firefox) | **Legacy / standalone** — a separate older scraper for Deutsche Börse (Frankfurt/Xetra/Tradegate/Eurex). Not integrated with `german_scraper/`. |

**Do they overlap?** Yes. The `.spec.js` files re-implement, in TypeScript,
the same venues now covered by Python: Berlin, ATHEX, Bank of Greece,
Bucharest, Munich, Lang & Schwarz, Börsen AG, Deutsche Börse. The Python
`german_scraper/` is a strict superset (it additionally covers Cboe, BME,
ICE pre/post, LuxSE, Wiener Börse, Bratislava). The `.spec.js` set uniquely
covers **Borsa Bulgaria** (and even that file is an 8-line stub).

**Independent or one calls the other?** Fully independent. There is no
cross-invocation — no Python file calls the `.spec.js` files and vice
versa, and `DeutscheBoerse/` shares no code with `german_scraper/`.

**Primary vs secondary.** `german_scraper/` (Python) is unambiguously
primary: it owns `pyproject.toml`'s `eu-scraper` entry point, the Dockerfile,
the k8s cronjob, and the 30-test suite. The `.spec.js` files and
`DeutscheBoerse/` are legacy.

**Duplication that should be consolidated.** The TypeScript `.spec.js`
scrapers duplicate Python logic and should be archived/deleted (port Borsa
Bulgaria to Python first). `DeutscheBoerse/` should be re-implemented as a
Playwright `Exchange` subclass. See `SUGGESTIONS.md` → Architecture.

---

## 2. Excel file dependency

`MORITZ APA 136.xlsx` and `Overview.xlsx` were checked against every
`.py`, `.js`, `.ts` and config file. **No scraper or module reads them** —
no `openpyxl`, `pandas.read_excel`, or path reference exists. (The only
grep hit for "Overview" is a coincidental substring of the LuxSE URL.)

**Conclusion:** the Excel files are unused. No `exchanges.json` / `config.yaml`
replacement is required. They have been **removed from git tracking**
(`excel_files/MORITZ APA 136.xlsx`, the `~$*.xlsx` Office lock files) and
the working-copy root files were deleted. They are already covered by the
`*.xlsx` rule in `.gitignore`.

---

## 3. Scraper status

### Confirmed working
- **Cboe Europe** — live debug run connected, accepted cookies, and
  correctly detected 55 hourly CSVs across BXE/CXE/DXE/APA. ✅
- **Storage layer** (adapters, schema, Parquet writer, ingest, manifest,
  Iceberg sink, metrics, DQ) — all 30 Python unit tests pass, including an
  end-to-end CSV→bronze→ingest→silver→Parquet round-trip. ✅

### Fixed during this audit
- **Stale `uv.lock`** — the committed lockfile was out of sync with
  `pyproject.toml`: it omitted `typer` (a declared dependency) and its
  transitive dep `annotated-doc`. `uv lock --check` fails against the old
  lock, which means the Dockerfile's `uv sync --frozen` build step would
  have **failed**. The lockfile was regenerated and now passes `--check`.
- **Bank of Greece** — selector `get_by_role("link", name="PreTradeHDAT.json i")`
  had a stray trailing `" i"` (a mangled case-insensitive flag), so the
  locator never matched and timed out after 30 s. Fixed to a proper
  case-insensitive regex. Live re-verification is **blocked** — the venue
  returns HTTP 403 (Akamai bot/geo protection) from this environment.
- **Börse München** — `_open_data_window` armed the popup waiter as a bare
  coroutine *after* the click (race) and clicked the link a second time when
  no popup appeared. Rewritten with `expect_popup`. Verified live: the
  post-trade flow detected 136 files cleanly. The **pre-trade** flow
  returned 0 files — a separate, pre-existing fragile-selector issue (the
  `MiFID II verzögerte pre-trade` link name or the `^pretrade\.` text
  filter no longer matches the live page); flagged, not fixed, as it needs
  live DOM inspection of the pre-trade page.

### Known issues / not verifiable here
- **Bank of Greece** is bot/geo-blocked (HTTP 403) from this environment —
  needs an EU IP / proxy to run.
- **Auth-gated scrapers not exercised** (no credentials, per audit rules):
  ICE pre/post (login + TOTP), LuxSE & Bratislava (IMAP email flow).
- **Wiener Börse** is documented as reCAPTCHA-prone (hence the stealth
  variant) — inherently fragile.
- **`DeutscheBoerse/` (legacy)** — will not run as-is: Windows-only
  hardcoded paths, an infinite `while True` loop, a likely `NameError` for
  an unmapped `subgroup`, and a directory-relative `import`.
- **`tests/*.spec.js`** — not run: they are live scrapers, and executing
  them would perform full multi-megabyte scrapes (violating the audit's
  "no full scrape" rule). `node_modules` is also not installed.

---

## 4. Overall code health

**Good.** The Python pipeline is well-structured and genuinely
production-minded: clean medallion separation, typed schemas with version
pinning, retry/backoff, a SQLite manifest doubling as catalog + DLQ,
pluggable storage backends, structured logging, metrics, DQ gates, and a
30-test suite that all passes. mypy-strict config is in place.

**Weak spots:**
- Two real scraper bugs found and fixed (above); fragile UI selectors are an
  inherent risk for the rest.
- Legacy debt: the TypeScript `.spec.js` scrapers and the Selenium
  `DeutscheBoerse/` scraper duplicate functionality and are unmaintained.
- `pyproject.toml` declares a bogus `asyncio` runtime dependency (stdlib);
  `requirements.txt` is stale and inconsistent with `pyproject.toml`.
- `uv.lock` was stale relative to `pyproject.toml` (missing `typer`) —
  fixed during this audit; keep lock and pyproject in sync going forward.
- Data files and OS noise were committed before `.gitignore` existed — now
  untracked (see §6).
- Broad `except Exception: pass` blocks can mask selector breakage.

See `SUGGESTIONS.md` for the full improvement backlog.

---

## 5. Running the project — new developer guide

> Note: the dev guide below is updated for the post-refactor state
> (see §8) — `config.json`, 58 tests, no `--prerelease` flag.

```bash
# 1. Python env (uv is the package manager; pyproject.toml is authoritative)
uv sync                      # core deps
uv sync --extra iceberg      # optional: Iceberg sink
uv sync --extra dev          # optional: pytest/mypy/ruff

# 2. Browser (Python Playwright)
python -m playwright install chromium   # Chromium only — already cached here

# 3. Run the test suite
python -m pytest tests_python/ -v        # 58 tests, all pass

# 4. Dry-run the storage layer (no bytes written)
python -m german_scraper.cli demo

# 5. Run scrapers (DEBUG/dry-run by default — logs, no downloads)
python -m german_scraper.cli scrape -e cboe
#   add --no-debug to actually download
#   PLAYWRIGHT_HEADLESS=true for servers

# 6. Bronze -> silver and ops
python -m german_scraper.cli ingest
python -m german_scraper.cli manifest-stats
python -m german_scraper.cli dq
```

Key things to know:
- **`scrape` is dry-run by default.** Real downloads need `--no-debug`.
- **Storage defaults to `DRY_RUN=true`.** Set `DRY_RUN=false` to write Parquet.
- **`config.json`** (repo root) tunes the default scraper set, concurrency,
  pacing, DQ thresholds and URLs — every key falls back to a built-in
  default. Storage/backend settings remain env-var driven (`STORAGE_BACKEND`,
  `MANIFEST_DSN`, `PLAYWRIGHT_HEADLESS`, …).
- Credentials for gated venues come from env vars: `ICE_EMAIL`/`ICE_PASSWORD`/
  `ICE_TOTP_SECRET`, `LUXSE_*` + `IMAP_*`, `BSSE_*` + `IMAP_*`.
- The maintained pipeline is `german_scraper/`; everything under `legacy/`
  is archived prototypes (see `legacy/README.md`).
- The Docker image (`Dockerfile`) is the canonical deployment artifact.

---

## 6. Repository hygiene actions taken

- Untracked from git (committed before `.gitignore` existed): `downloads/`
  (all leftover scraped data + `.DS_Store`), `excel_files/MORITZ APA 136.xlsx`,
  the `~$*.xlsx` Office lock files, and all `.DS_Store` files.
- Deleted leftover downloaded data from disk (~1.9 MB: Bucharest BVB Excel
  files, Bank of Greece JSON, a Borsa Bulgaria `batch` blob) — these remain
  recoverable from git history.
- `.gitignore` itself was already complete (covers `downloads/`, `data/`,
  `*.xlsx`, `.venv/`, `eu-exchange-env/`, browser caches, `.DS_Store`,
  `manifest.db`) — no rule changes were needed, only un-tracking.

---

## 7. Storage estimate — data per day if all scrapers ran continuously

Rough order-of-magnitude only (file sizes were not measured live to respect
the audit's no-download rule; based on observed leftover files and per-venue
file counts):

| Venue group | Approx. bronze/day |
|---|---|
| Deutsche Börse (legacy, 4 markets, `.json.gz`, ~hourly) | ~100–500 MB |
| Börse Berlin (pre+post, ≤50 CSV/run) | ~50–200 MB |
| Cboe Europe (~55 hourly CSV) | ~10–30 MB |
| ICE pre+post (paginated CSV-per-row) | ~10–50 MB |
| Munich / LSX / Börsen AG (CSV) | ~5–20 MB each |
| Bucharest (3 Excel files, observed ~1.2 MB) | ~1–3 MB |
| ATHEX / BME / Wiener / LuxSE / Bratislava | ~1–10 MB each |
| Bank of Greece (2 JSON, observed ~26 KB) | <0.1 MB |

**Total bronze ≈ 0.3–1 GB/day** (dominated by Deutsche Börse and Berlin).
Silver Parquet is Snappy-compressed and narrower — expect roughly **30–60%
of bronze volume** on top, i.e. another ~0.1–0.6 GB/day. Plan for **on the
order of 1 GB/day** combined, and budget storage growth accordingly (a
compaction + retention job is recommended — see `SUGGESTIONS.md`).

---

## 8. Architecture refactor (implemented after the audit)

All six "Architecture improvements" from `SUGGESTIONS.md` were carried
out. The work was done incrementally with the test suite run after each
step; it grew from 30 to **58 passing tests**.

**What changed**

1. **Python-only active tree.** The 13 TypeScript `.spec.js` prototypes
   and the TS harness (`playwright.config.ts`, `package.json`,
   `package-lock.json`, `tests-examples/`) moved to
   `legacy/playwright-prototypes/`. The Selenium Deutsche Börse scraper
   moved to `legacy/deutsche-boerse-selenium/`. `legacy/README.md`
   documents the mapping. Nothing in `german_scraper/` imports from
   `legacy/`.

2. **Borsa Bulgaria ported** → `german_scraper/exchanges/bulgaria.py`
   (`BorsaBulgaria`). It was the only venue the TS prototypes covered
   that the Python pipeline lacked. Live debug run: connects, dismisses
   consent, locates the CSV export control. ✅

3. **Deutsche Börse re-implemented** → `german_scraper/exchanges/deutsche_boerse.py`
   (`DeutscheBoerse`) — a Playwright `Exchange` subclass replacing the
   Selenium version. Live debug run: connects, accepts cookies, opens
   the "Xetra – Pre-Trade File service" popup, detects **1875 `.json.gz`
   files**. ✅ The set of rows to visit is config-driven.

4. **Config file.** `config.json` + `german_scraper/settings.py` are now
   the single source for `default_enabled`, `concurrency`, per-venue
   `pacing`, `dq_rules` and exchange `urls`. `cli.py`, `core/dq.py`,
   `berlin.py`/`berlin_cron.py` and every venue URL constant read from
   it, each with a built-in fallback so a missing/partial config never
   breaks the pipeline. Covered by `tests_python/test_settings.py`.

5. **Dependency hygiene.** Removed the bogus `asyncio` PyPI dependency
   (`uv remove asyncio`); `requirements.txt` moved into
   `legacy/deutsche-boerse-selenium/`; the placeholder `main.py` deleted.
   `uv.lock` regenerated — `uv lock --check` passes, and the redundant
   `--prerelease=allow` flag was dropped from the Dockerfile / CI / docs
   (the default-mode lock resolves everything, incl. the Iceberg extra).

6. **CI.** `.github/workflows/playwright.yml` (which ran the live
   `.spec.js` scrapers on every push) was replaced by
   `.github/workflows/ci.yml` — a uv + `pytest tests_python/` job.

**Registry:** 16 → **18 scrapers** (`bulgaria`, `deutsche-boerse` added).

**Tests:** 30 → **58**, all passing — added `test_settings.py` (7) and
`test_scrapers.py` (registry contract + the two new scrapers).

**Regression check:** full `pytest` green, `uv lock --check` green,
`uv sync --frozen --extra dev --extra iceberg` green, and debug-mode
live runs of Cboe, Bulgaria and Deutsche Börse all connect and extract
correctly. No files left in `downloads/`.
