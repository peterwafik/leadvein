import json
from sqlmodel import Session
from app.core.db import init_db, Lead, LeadCategoryLink
from app.core.leadcats import sync_lead_categories, lead_ids_for_categories


def test_sync_and_query_categories():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        lead = Lead(business_name="X",
                    category_keys_json=json.dumps(["restaurant", "cafe"]))
        s.add(lead); s.commit(); s.refresh(lead)
        sync_lead_categories(s, lead)
        assert lead.id in lead_ids_for_categories(s, ["restaurant"])
        assert lead_ids_for_categories(s, ["gym"]) == set()
        # re-sync after a category change removes stale links (idempotent)
        lead.category_keys_json = json.dumps(["gym"]); s.add(lead); s.commit()
        sync_lead_categories(s, lead)
        assert lead.id not in lead_ids_for_categories(s, ["restaurant"])
        assert lead.id in lead_ids_for_categories(s, ["gym"])


def test_lead_has_perf_indexes():
    idx_cols = {c.name for idx in Lead.__table__.indexes for c in idx.columns}
    for col in ("score_total", "city", "country", "source_key", "date_last_verified"):
        assert col in idx_cols
