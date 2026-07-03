"""250 k-row estimate performance benchmark.

Usage (env-gated — skipped in the default test run):

    # PowerShell
    $env:RUN_SCALE_BENCH='1'; python -m pytest tests/test_estimate_benchmark.py -v -s

    # bash / CI
    RUN_SCALE_BENCH=1 python -m pytest tests/test_estimate_benchmark.py -v -s

The benchmark seeds 250 k synthetic leads ONCE into a dedicated throwaway
SQLite file (NOT the shared conftest test DB) then runs 20 timed estimate()
calls. p95 of those calls must be < 0.5 s; a search-page-shaped call (country
+ score pre-filter + profile SQL clauses) must be < 0.3 s.

Mark: slow  — run individually, not in the default `pytest tests/` pass.
"""
from __future__ import annotations

import json
import os
import random
import statistics
import tempfile
import time
import uuid

import pytest

# ── Module-level skip guard ────────────────────────────────────────────────────
if not os.environ.get("RUN_SCALE_BENCH"):
    pytest.skip("set RUN_SCALE_BENCH=1 to run the 250 k benchmark",
                allow_module_level=True)

# ── Imports that only matter when the benchmark actually runs ──────────────────
from sqlmodel import Session, SQLModel
from sqlalchemy import event

from app.core.db import Lead, init_db
from app.core.targeting.estimate import estimate
from app.quality.ordinals import apply_tier_columns, FIELDS
from app.quality.profiles.baseline import BASELINE
from app.quality.profiles.registry import get as get_profile
from app.quality.sql_gate import profile_clauses
from app.targeting.runtime import register_targeting_runtime

# ── Ensure targeting predicates are registered ────────────────────────────────
register_targeting_runtime()

# ── Build dedicated throwaway engine (not the shared conftest DB) ─────────────
_DB_FILE = os.path.join(tempfile.gettempdir(),
                        f"leadvault_bench_{uuid.uuid4().hex[:8]}.db")
_BENCH_ENGINE = init_db(f"sqlite:///{_DB_FILE}")

# ── Seed 250 k synthetic leads ────────────────────────────────────────────────
_COUNTRIES = ["GB", "DE", "FR", "ES", "IT", "NL", "SE", "NO", "PL", "US"]
_CITIES = ["CityA", "CityB", "CityC", "CityD", "CityE"]
_TIERS = ["absent", "present", "validated"]
_PER_COUNTRY = 25_000
_BATCH = 5_000

random.seed(0)


def _make_lead(i: int, country: str) -> Lead:
    tier_p = random.choice(_TIERS)
    tier_ph = random.choice(_TIERS)
    tier_em = random.choice(_TIERS)
    val = {
        "phone":   {"tier": tier_ph},
        "email":   {"tier": tier_em},
        "address": {"tier": random.choice(_TIERS)},
        "website": {"tier": random.choice(_TIERS)},
        "profile": {"tier": tier_p},
    }
    lead = Lead(
        business_name=f"Bench-{country}-{i}",
        country=country,
        city=random.choice(_CITIES),
        score_total=random.randint(0, 100),
        validation_json=json.dumps(val),
        retention_expiry="2999-01-01T00:00:00+00:00",
    )
    apply_tier_columns(lead, val)
    return lead


def _seed() -> None:
    with Session(_BENCH_ENGINE) as s:
        batch = []
        n = 0
        for country in _COUNTRIES:
            for i in range(_PER_COUNTRY):
                batch.append(_make_lead(n, country))
                n += 1
                if len(batch) >= _BATCH:
                    s.add_all(batch)
                    s.commit()
                    batch = []
        if batch:
            s.add_all(batch)
            s.commit()


_seed()   # runs once at module import — before any test function

# ── Compositions ──────────────────────────────────────────────────────────────
_COMP_COUNTRY = {
    "op": "AND",
    "nodes": [{"predicate": "geo.country", "params": {"value": "GB"}}],
}

_COMP_SEARCH = {
    "op": "AND",
    "nodes": [
        {"predicate": "geo.country",      "params": {"value": "GB"}},
        {"predicate": "quality.min_score", "params": {"min": 50}},
    ],
}


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.slow
def test_estimate_p95_250k():
    """p95 of 20 estimate calls (country + BASELINE profile SQL clauses) < 0.5 s."""
    prof = get_profile("baseline")
    ctx = {"quality_profile": prof, "sql_clauses": profile_clauses(prof) or []}
    times = []
    with Session(_BENCH_ENGINE) as s:
        for _ in range(20):
            t0 = time.perf_counter()
            result = estimate(s, 1, _COMP_COUNTRY, ctx=ctx)
            times.append(time.perf_counter() - t0)
    times.sort()
    p95 = times[int(len(times) * 0.95)]   # index 19 of 20 = max (worst case)
    print(f"\n[bench] estimate 20-call p95={p95:.3f}s  count={result['count']}")
    assert p95 < 0.5, (
        f"estimate p95 {p95:.3f}s >= 0.5s at 250 k rows — "
        "see DONE_WITH_CONCERNS in task-10-report.md"
    )


@pytest.mark.slow
def test_search_shaped_call_250k():
    """Single search-page-shaped call (country + score SQL pushdown + profile clauses) < 0.3 s."""
    prof = get_profile("baseline")
    ctx = {"quality_profile": prof, "sql_clauses": profile_clauses(prof) or []}
    with Session(_BENCH_ENGINE) as s:
        t0 = time.perf_counter()
        result = estimate(s, 1, _COMP_SEARCH, ctx=ctx)
        elapsed = time.perf_counter() - t0
    print(f"\n[bench] search-shaped call {elapsed:.3f}s  count={result['count']}")
    assert elapsed < 0.3, (
        f"search-shaped call {elapsed:.3f}s >= 0.3s at 250 k rows — "
        "see DONE_WITH_CONCERNS in task-10-report.md"
    )
