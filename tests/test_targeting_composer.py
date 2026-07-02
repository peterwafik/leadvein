import json
from sqlmodel import Session
from app.core.db import init_db, Lead, _now
from app.core.leadcats import sync_lead_categories
from app.core.targeting import registry
from app.targeting.runtime import register_targeting_runtime
from app.core.targeting.coverage import recompute_coverage
from app.core.targeting.composer import predicate_options


def test_options_are_data_driven():
    registry.clear(); register_targeting_runtime()
    e = init_db("sqlite://")
    with Session(e) as s:
        lead = Lead(business_name="A", country="GB", city="Oxford", phone="1", score_total=80,
                    category_keys_json=json.dumps(["cafe"]), date_last_verified=_now(),
                    intent_json="{}")   # NOTE: no intent signals populated
        s.add(lead); s.commit(); s.refresh(lead); sync_lead_categories(s, lead)
        recompute_coverage(s)
        opt = predicate_options(s)
        avail = {d["key"] for d in opt["available"]}
        unavail = {d["key"] for d in opt["unavailable"]}
        assert "geo.country" in avail and "geo.city" in avail and "quality.min_score" in avail
        # web.has_signal reads "intent" which is NOT populated -> unavailable (greyed), not faked
        assert "web.has_signal" in unavail
        assert avail.isdisjoint(unavail)
