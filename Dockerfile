# EU exchange scraper — production image
#
# Multi-stage build:
#   1. ``builder``  — uv resolves and installs deps into a virtualenv.
#   2. ``runtime``  — Playwright's official Python image gives us
#                     Chromium + system fonts + libs preinstalled.
#
# The image runs as a non-root user, writes manifests to /var/lib/eu-scraper,
# and reads scrape config from env. Mount your manifest / warehouse volumes
# at /var/lib/eu-scraper and /var/lib/eu-scraper/warehouse respectively.

# ── builder ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY german_scraper/ ./german_scraper/

# Install everything except the iceberg extra by default; flip
# ``ICEBERG=1`` at build time to include it.
ARG ICEBERG=0
RUN if [ "$ICEBERG" = "1" ]; then \
      uv sync --frozen --extra iceberg --prerelease=allow; \
    else \
      uv sync --frozen; \
    fi

# ── runtime ─────────────────────────────────────────────────────────────
FROM mcr.microsoft.com/playwright/python:v1.59.0-noble AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    LOG_FORMAT=json \
    LOG_LEVEL=INFO \
    PLAYWRIGHT_HEADLESS=true \
    DRY_RUN=false \
    STORAGE_BACKEND=local \
    STORAGE_LOCAL_ROOT=/var/lib/eu-scraper \
    MANIFEST_DSN=/var/lib/eu-scraper/manifest.db \
    ICEBERG_WAREHOUSE=/var/lib/eu-scraper/warehouse

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app
WORKDIR /app

# Non-root runtime user owns the data dir.
RUN useradd --create-home --shell /bin/bash scraper \
 && mkdir -p /var/lib/eu-scraper/warehouse \
 && chown -R scraper:scraper /var/lib/eu-scraper /app
USER scraper

ENTRYPOINT ["python", "-m", "german_scraper.cli"]
CMD ["scrape", "--exchanges", "berlin,cboe", "--no-debug"]
