import json
from sqlmodel import Session
from app.core.db import (init_db, Lead, _now, SuppressionList, SuppressionEntry)
from app.core.marketplace import search, estimate
from app.core.recipes import DEFAULT_FILTERS


def _seed(s):
    s.add(Lead(business_name="Diner", category_keys_json=json.dumps(["restaurant"]),
               city="London", phone="1", website_url="https://keep.com", score_total=85,
               date_last_verified=_now(), price_credits=3))
    s.add(Lead(business_name="Suppressed", category_keys_json=json.dumps(["restaurant"]),
               city="London", phone="1", website_url="https://blocked.com",
               score_total=88, date_last_verified=_now(), price_credits=3))
    s.commit()
    lst = SuppressionList(buyer_account_id=1, name="mine")
    s.add(lst); s.commit(); s.refresh(lst)
    s.add(SuppressionEntry(list_id=lst.id, kind="domain", value="blocked.com"))
    s.commit()


def test_search_excludes_suppressed_and_masks():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        _seed(s)
        f = {**DEFAULT_FILTERS, "categories": ["restaurant"], "city": "London"}
        res = search(s, 1, f)
        assert len(res) == 1                       # suppressed one excluded
        blob = json.dumps(res).lower()
        assert "keep.com" not in blob and "diner" not in blob   # masked
        assert res[0]["score_total"] == 85
        est = estimate(s, 1, f)
        assert est["count"] == 1 and est["score_buckets"]["80+"] == 1
        assert est["total_price_credits"] == 3
