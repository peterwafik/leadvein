import json
from sqlmodel import Session
from app.core.db import init_db, Lead, _now
from app.core.recipes import matching_leads, DEFAULT_FILTERS
from app.core.leadcats import sync_lead_categories


def _seed(s):
    diner = Lead(business_name="Diner", category_keys_json=json.dumps(["restaurant"]),
                 city="London", phone="1", website_url="https://a.com", score_total=80,
                 date_last_verified=_now())
    s.add(diner); s.commit(); s.refresh(diner)
    sync_lead_categories(s, diner)
    cafe = Lead(business_name="Cafe", category_keys_json=json.dumps(["cafe"]),
                city="London", phone="", website_url="https://b.com", score_total=40,
                date_last_verified=_now())
    s.add(cafe); s.commit(); s.refresh(cafe)
    sync_lead_categories(s, cafe)


def test_filters_category_score_contact_and_optout():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        _seed(s)
        f = {**DEFAULT_FILTERS, "categories": ["restaurant"], "min_score": 50,
             "require_phone": True, "city": "London"}
        res = matching_leads(s, f)
        names = [l.business_name for l in res]
        assert names == ["Diner"]          # cafe (low score), optout excluded
