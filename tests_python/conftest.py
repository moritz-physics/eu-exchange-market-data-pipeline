"""Pytest fixtures shared across the storage / pipeline test suite."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure the repo root is importable when pytest is invoked from anywhere.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_manifest(tmp_path: Path):
    """Fresh SQLite manifest in a tmpdir."""
    from german_scraper.core.manifest_db import Manifest
    return Manifest(tmp_path / "manifest.db")


@pytest.fixture
def tmp_warehouse(tmp_path: Path) -> Path:
    """Local warehouse root for parquet writes."""
    p = tmp_path / "warehouse"
    p.mkdir()
    return p


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    """Prevent tests from clobbering or being affected by user env state."""
    # Pin DRY_RUN = false unless a test sets it; metrics aren't affected.
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("MANIFEST_DSN", str(tmp_path / "manifest.db"))
    yield
