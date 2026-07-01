import json
from sqlmodel import Session, select
from app.core.db import init_db, Lead, _now
from app.core.leadcats import sync_lead_categories
from app.core.targeting import registry
from app.targeting.runtime import register_targeting_runtime
from app.core.targeting.composition import matching_by_composition, selects
from app.core.targeting.view import lead_view


def _seed(s):
    a = Lead(business_name="A", country="GB", city="London", score_total=90, phone="1",
             category_keys_json=json.dumps(["cafe"]), date_last_verified=_now(),
             intent_json=json.dumps({"ecommerce_detected": True}))
    b = Lead(business_name="B", country="GB", city="Leeds", score_total=40, phone="",
             category_keys_json=json.dumps(["gym"]), date_last_verified=_now(),
             intent_json="{}")  # un-enriched
    c = Lead(business_name="C", country="FR", city="Paris", score_total=95, phone="3",
             category_keys_json=json.dumps(["cafe"]), date_last_verified=_now(),
             intent_json=json.dumps({"ecommerce_detected": False}))
    for x in (a, b, c):
        s.add(x)
    s.commit()
    for x in (a, b, c):
        s.refresh(x); sync_lead_categories(s, x)
    return a, b, c


def _pure_python(s, comp):
    return sorted(l.business_name for l in s.exec(select(Lead)).all()
                  if selects(lead_view(l), comp))


def test_matcher_correct_and_parity():
    e = init_db("sqlite://")
    registry.clear(); register_targeting_runtime()
    with Session(e) as s:
        _seed(s)
        comp = {"op": "AND", "nodes": [
            {"predicate": "geo.country", "params": {"value": "GB"}},
            {"predicate": "quality.min_score", "params": {"min": 50}},
            {"predicate": "category.any", "params": {"in": ["cafe"]}}]}
        got = sorted(l.business_name for l in matching_by_composition(s, comp))
        assert got == ["A"]                       # GB + score>=50 + cafe
        assert got == _pure_python(s, comp)       # INV-5 parity
        # NOT ecommerce excludes the un-enriched B (INV-1 through the matcher)
        notc = {"op": "AND", "nodes": [
            {"predicate": "geo.country", "params": {"value": "GB"}},
            {"predicate": "web.has_signal", "params": {"signal": "ecommerce_detected"},
             "negate": True}]}
        assert sorted(l.business_name for l in matching_by_composition(s, notc)) == []
        assert sorted(l.business_name for l in matching_by_composition(s, notc)) == _pure_python(s, notc)
