import json
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
from app.core.db import (init_db, Lead, LeadCategoryLink, BuyerAccount, User,
                         PurchasedLead, _now)
from app.core.retention import (RETENTION_DAYS, expiry_for, is_expired,
                               purge_expired, expired_count)
from app.core.leadcats import sync_lead_categories
from app.core.marketplace import search
from app.core.recipes import DEFAULT_FILTERS


def _past():
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def test_expiry_for_and_is_expired():
    assert expiry_for(None) is None
    verified = "2020-03-01T00:00:00+00:00"   # post-leap-day: +365 lands in 2021
    exp = expiry_for(verified)
    assert exp > verified and exp.startswith("2021")          # +365 days
    assert is_expired(Lead(retention_expiry=_past())) is True
    assert is_expired(Lead(retention_expiry=None)) is False    # no expiry set -> not expired
    future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    assert is_expired(Lead(retention_expiry=future)) is False


def test_search_excludes_expired():
    from app.core.serve_filters import clear as _gate_off
    _gate_off()  # gate-off: this test exercises retention expiry enforcement, not the quality gate
    engine = init_db("sqlite://")
    with Session(engine) as s:
        lead = Lead(business_name="Stale", category_keys_json=json.dumps(["restaurant"]),
                    city="London", phone="1", score_total=90, date_last_verified=_past(),
                    retention_expiry=_past())
        s.add(lead); s.commit(); s.refresh(lead)
        sync_lead_categories(s, lead)
        f = {**DEFAULT_FILTERS, "categories": ["restaurant"], "city": "London"}
        assert search(s, 1, f) == []     # expired record is not served


def test_purge_removes_unsold_keeps_sold():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        unsold = Lead(business_name="Unsold", category_keys_json=json.dumps(["cafe"]),
                      retention_expiry=_past())
        sold = Lead(business_name="Sold", category_keys_json=json.dumps(["cafe"]),
                    retention_expiry=_past())
        s.add(unsold); s.add(sold); s.commit(); s.refresh(unsold); s.refresh(sold)
        sync_lead_categories(s, unsold); sync_lead_categories(s, sold)
        s.add(PurchasedLead(buyer_account_id=1, lead_id=sold.id)); s.commit()
        assert expired_count(s) == 2
        removed = purge_expired(s)
        assert removed == 1                                   # only the unsold expired lead
        remaining = [l.business_name for l in s.exec(select(Lead)).all()]
        assert remaining == ["Sold"]
        # the purged lead's category links are gone too
        assert s.exec(select(LeadCategoryLink).where(
            LeadCategoryLink.lead_id == unsold.id)).all() == []
