"""Test isolation: point the app at a throwaway per-process SQLite file BEFORE any
test imports `app.leadvault`. This keeps the web tests (which use the shared app
engine) from touching — or being polluted by — the dev `leadvault.db`, and makes the
suite self-contained: re-running it without deleting any DB always starts clean.

This module's top-level code runs at pytest startup, before test modules are
imported, so the `LEADVAULT_DB` env var is set before `app.leadvault` binds its engine.
"""
from __future__ import annotations

import os
import tempfile

_DB_PATH = os.path.join(tempfile.gettempdir(), f"leadvault_pytest_{os.getpid()}.db")

# Start every session from an empty DB.
if os.path.exists(_DB_PATH):
    os.remove(_DB_PATH)

os.environ["LEADVAULT_DB"] = "sqlite:///" + _DB_PATH.replace("\\", "/")

import pytest


@pytest.fixture(scope="session", autouse=True)
def _remove_test_db():
    yield
    try:
        os.remove(_DB_PATH)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.web.ratelimit import reset
    reset()
    yield


@pytest.fixture(autouse=True)
def _quality_gate_on():
    """Gate ON by default, mirroring production; tests that exercise non-quality concerns
    opt OFF explicitly with a reason (call app.core.serve_filters.clear() at test start
    with a comment explaining why quality is orthogonal to what the test exercises)."""
    import app.core.serve_filters as _sf
    import app.quality.runtime as _qr
    import app.quality.serve_gate as _sg
    from app.quality.profiles.baseline import BASELINE
    _sf.clear()
    _qr.register_quality_runtime()
    _sg.set_gate_profile(BASELINE)
    yield
