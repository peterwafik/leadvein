import json
from sqlmodel import Session
from app.core.db import init_db, Lead, OptOutRequest, _now
from app.core.leadcats import sync_lead_categories
from app.core.targeting import registry
from app.targeting.runtime import register_targeting_runtime
from app.core.targeting.estimate import estimate


def test_estimate_masks_and_respects_compliance():
    from app.core.serve_filters import clear as _gate_off
    _gate_off()  # gate-off: this test exercises opt-out compliance and masking in estimate, not the quality gate
    e = init_db("sqlite://")
    registry.clear(); register_targeting_runtime()
    with Session(e) as s:
        keep = Lead(business_name="Keep", country="GB", city="London", score_total=90, phone="1",
                    public_email="info@keep.com", website_url="https://keep.com",
                    category_keys_json=json.dumps(["cafe"]), date_last_verified=_now())
        gone = Lead(business_name="Gone", country="GB", city="London", score_total=88, phone="2",
                    website_url="https://gone.com",
                    category_keys_json=json.dumps(["cafe"]), date_last_verified=_now())
        s.add(keep); s.add(gone); s.commit()
        for x in (keep, gone):
            s.refresh(x); sync_lead_categories(s, x)
        s.add(OptOutRequest(kind="domain", value="gone.com", applied=True)); s.commit()
        comp = {"op": "AND", "nodes": [{"predicate": "geo.country", "params": {"value": "GB"}}]}
        est = estimate(s, 1, comp)
        assert est["count"] == 1                              # opted-out 'Gone' excluded
        blob = json.dumps(est["samples"])
        assert "Keep" not in blob and "info@keep.com" not in blob and "keep.com" not in blob  # masked
        assert sum(est["score_distribution"].values()) == 1
        assert sum(est["freshness_distribution"].values()) == 1
