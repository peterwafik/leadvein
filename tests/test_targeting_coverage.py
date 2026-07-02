import json
from sqlmodel import Session
from app.core.db import init_db, Lead, _now
from app.core.leadcats import sync_lead_categories
from app.core.targeting import registry
from app.targeting.runtime import register_targeting_runtime
from app.core.targeting.coverage import (recompute_coverage, populated_paths, coverage_pct,
                                         TRACKED_PATHS)


def _seed(s):
    a = Lead(business_name="A", country="GB", city="Oxford", phone="1", score_total=80,
             category_keys_json=json.dumps(["cafe"]), date_last_verified=_now(),
             intent_json=json.dumps({"ssl": True}))
    b = Lead(business_name="B", country="GB", city="", phone="", score_total=40,
             category_keys_json=json.dumps(["gym"]), intent_json="{}")
    for x in (a, b):
        s.add(x)
    s.commit()
    for x in (a, b):
        s.refresh(x); sync_lead_categories(s, x)


def test_coverage_reflects_real_inventory():
    registry.clear(); register_targeting_runtime()
    # Register a test predicate that tracks intent.ssl
    class _TestSSL:
        key = "test.ssl"; group = "test"; label = "Test SSL"; reads = ["intent.ssl"]; params_schema = {}
        def matches(self, view, params): return True
    registry.register(_TestSSL())

    e = init_db("sqlite://")
    with Session(e) as s:
        _seed(s)
        assert "country" in TRACKED_PATHS()            # union of predicate reads
        recompute_coverage(s)
        pp = populated_paths(s)
        assert "country" in pp and "city" in pp and "phone" in pp   # A has these
        assert "intent.ssl" in pp                                   # A has it
        # 2 leads, both country=GB -> 100%; city populated on 1 of 2 -> 50%
        assert coverage_pct(s, "country") == 100.0
        assert coverage_pct(s, "city") == 50.0
