"""SQL gate: profile_clauses() produces a list of SQLAlchemy WHERE clauses
that PRE-NARROW Lead rows by tier columns.  The Python gate (clears_gate) stays
authoritative on every lead — the SQL clauses are a superset filter only (INV-Q1).

Run the property test with the full quality runtime registered (conftest autouse
fixture calls register_quality_runtime before each test).
"""
from __future__ import annotations

import json
import random

from sqlmodel import Session

import app.leadvault as lv
from app.core.db import Lead
from app.core.targeting.estimate import estimate
from app.quality.ordinals import apply_tier_columns
from app.quality.profiles.registry import all_keys, get as get_profile
from app.quality.sql_gate import profile_clauses


def test_clauses_for_registered_profiles():
    for key in all_keys():
        clauses = profile_clauses(get_profile(key))
        assert clauses is not None            # all registered profiles are tier-expressible
        assert len(clauses) == len(get_profile(key).required)


def test_unknown_field_returns_none():
    from app.quality.profiles.base import QualityProfile
    weird = QualityProfile(key="w", label="w", required={"attributes.size_band": "validated"})
    assert profile_clauses(weird) is None


def _random_lead(i):
    tiers = ["absent", "present", "validated"]
    val = {f: {"tier": random.choice(tiers)}
           for f in ("phone", "email", "address", "website", "profile")}
    lead = Lead(business_name=f"SG-{i}", city="Gateville", country="GB",
                score_total=random.randint(0, 100),
                validation_json=json.dumps(val),
                retention_expiry="2999-01-01T00:00:00+00:00")
    apply_tier_columns(lead, val)
    return lead


def test_sql_narrowing_equals_python_gate():          # INV-Q1 superset proof
    random.seed(42)
    with Session(lv.engine) as s:
        for i in range(120):
            s.add(_random_lead(i))
        s.commit()
        comp = {"op": "AND", "nodes": [
            {"predicate": "geo.city_any", "params": {"in": ["Gateville"]}}]}
        for key in all_keys():
            prof = get_profile(key)
            with_sql = estimate(s, 1, comp, ctx={
                "quality_profile": prof,
                "sql_clauses": profile_clauses(prof) or []})
            without_sql = estimate(s, 1, comp, ctx={"quality_profile": prof})
            assert with_sql["count"] == without_sql["count"], key
            assert with_sql["score_distribution"] == without_sql["score_distribution"], key
