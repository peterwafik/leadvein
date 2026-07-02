import json
from sqlmodel import Session
from app.core.db import init_db, Lead, _now
from app.core.targeting import registry
from app.targeting.runtime import register_targeting_runtime
from app.core.targeting.view import lead_view


def _mk(city): return Lead(business_name="B", city=city, country="GB", phone="1", score_total=50,
                           category_keys_json="[]", date_last_verified=_now())


def test_geo_city_any_matches_any_of_list():
    registry.clear(); register_targeting_runtime()
    p = registry.get("geo.city_any")
    assert p.matches(lead_view(_mk("Oxford")), {"in": ["Oxford", "Norwich"]}) is True
    assert p.matches(lead_view(_mk("Bristol")), {"in": ["Oxford", "Norwich"]}) is False
    assert p.matches(lead_view(_mk("")), {"in": ["Oxford"]}) is None          # tri-state absent
    assert p.matches(lead_view(_mk("Oxford")), {"in": []}) is None            # empty selection
