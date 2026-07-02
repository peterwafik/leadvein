import json
from sqlmodel import Session
from app.core.db import init_db, Lead, _now
from app.core.leadcats import sync_lead_categories
from app.core.targeting import registry
from app.targeting.runtime import register_targeting_runtime
from app.quality.runtime import register_quality_runtime
from app.core.targeting.coverage import recompute_coverage
from app.core.targeting.estimate import estimate
from app.quality.profiles.registry import get as get_profile
from tests.quality_helpers import hot_validation_json, phone_validated_json, email_only_validated_json


def _lead(s, name, val):
    l = Lead(business_name=name, category_keys_json=json.dumps(["cafe"]), city="Oxford", phone="1",
             score_total=80, date_last_verified=_now(), price_credits=3, validation_json=val)
    s.add(l); s.commit(); s.refresh(l); sync_lead_categories(s, l); return l


def test_campaign_profile_narrows_on_top_of_baseline():
    registry.clear(); register_targeting_runtime(); register_quality_runtime()
    e = init_db("sqlite://")
    with Session(e) as s:
        _lead(s, "PhoneHot", phone_validated_json())        # clears baseline AND utilities (phone validated)
        _lead(s, "EmailOnly", email_only_validated_json())  # clears baseline (email validated) but NOT utilities
        recompute_coverage(s)
        comp = {"op":"AND","nodes":[{"predicate":"geo.city","params":{"value":"Oxford"}}]}
        base = estimate(s, 1, comp)                          # ctx=None -> baseline only
        util = estimate(s, 1, comp, ctx={"quality_profile": get_profile("utilities")})
        assert base["count"] == 2                            # both clear baseline
        assert util["count"] == 1                            # utilities requires validated phone -> EmailOnly dropped
