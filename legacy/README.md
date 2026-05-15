# Legacy code (archived — not maintained)

This directory holds the **first-generation scrapers**, kept for
reference only. They are **superseded** by the maintained Python
pipeline in [`german_scraper/`](../german_scraper). Nothing in the
active pipeline imports from here, and CI does not run any of it.

## `playwright-prototypes/`

The original Playwright **TypeScript** scrapers, written as `*.spec.js`
"tests". They are not unit tests — each one performs a live download
from a venue. Every venue they covered has since been re-implemented as
a proper `Exchange` subclass in `german_scraper/exchanges/`:

| Prototype | Replaced by |
|---|---|
| `borsa_bulgaria_test.spec.js` | `exchanges/bulgaria.py` |
| `deutsche_boerse.spec.js` | `exchanges/deutsche_boerse.py` |
| `romania_boerse.spec.js` | `exchanges/bucharest.py` |
| `greece_athex_test.spec.js` | `exchanges/athex.py` |
| `greece_national_bank.spec.js` | `exchanges/bank_of_greece.py` |
| `boerse_berlin_pre/post.spec.js`, `berlin_pre_backup.spec.js` | `exchanges/berlin.py` |
| `boerse_munich.spec.js` | `exchanges/munich.py` |
| `boerse_lange_schwarz.spec.js` | `exchanges/lsx.py` |
| `boersen_ag_test.spec.js` | `exchanges/boersenag.py` |
| `demo_1.spec.js`, `tests-examples/` | (Playwright scaffolding — no replacement) |

`playwright.config.ts`, `package.json` and `package-lock.json` are the
TypeScript harness for those prototypes.

## `deutsche-boerse-selenium/`

The original Deutsche Börse scraper, built on **Selenium + Firefox**.
Re-implemented as a Playwright `Exchange` subclass in
`german_scraper/exchanges/deutsche_boerse.py`. The old version had
Windows-only hardcoded paths, an infinite run loop, and a
directory-relative import — it will not run unmodified. `requirements.txt`
here lists that scraper's original dependencies; the maintained pipeline
uses `pyproject.toml` at the repo root.

---

To restore any of this, the files are also recoverable from git history.
