import json
import re

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import app.leadvault as lv
from app.core.db import (Lead, BuyerAccount, User, OptOutRequest, PurchasedLead, _now)
from app.core.leadcats import sync_lead_categories
from app.core.marketplace import search
from app.core.recipes import DEFAULT_FILTERS
from app.core.purchasing import unlock_lead, grant_credits, LeadSuppressed
from app.core.export_leads import export_purchased_csv
from app.core.compliance import lead_opted_out


def _csrf(c, path):
    m = re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text)
    return m.group(1) if m else ""


def test_optout_form_reachable_without_login():
    r = TestClient(lv.app).get("/opt-out")
    assert r.status_code == 200
    assert "Opt out of LeadVault" in r.text


def test_public_optout_suppresses_across_search_preview_unlock_export():
    from app.core.serve_filters import clear as _gate_off
    _gate_off()  # gate-off: this test exercises public opt-out suppression across all surfaces, not the quality gate
    c = TestClient(lv.app)
    with Session(lv.engine) as s:
        ba = BuyerAccount(company_name="B", credits=0, compliance_ack_at=_now())
        s.add(ba); s.commit(); s.refresh(ba)
        u = User(email="optoutbuyer@x.com", password_hash="x", role="buyer",
                 buyer_account_id=ba.id)
        s.add(u); s.commit(); s.refresh(u)
        grant_credits(s, ba.id, 50)
        lead = Lead(business_name="OptMe Ltd",
                    category_keys_json=json.dumps(["restaurant"]), city="London",
                    phone="+44 20 9999 0000", public_email="hi@optme.com",
                    website_url="https://optme.com", score_total=95,
                    date_last_verified=_now(), price_credits=3)
        s.add(lead); s.commit(); s.refresh(lead)
        sync_lead_categories(s, lead)
        s.commit()  # commit category links before opening the next session
        lead_id, ba_id, u_id = lead.id, ba.id, u.id

    f = {**DEFAULT_FILTERS, "categories": ["restaurant"], "city": "London"}

    # visible BEFORE opt-out
    with Session(lv.engine) as s:
        assert len(search(s, ba_id, f)) >= 1

    # submit the PUBLIC opt-out (no login) for the business domain
    token = _csrf(c, "/opt-out")
    sub = c.post("/opt-out", data={"kind": "domain", "value": "optme.com",
                 "csrf_token": token}, follow_redirects=False)
    assert sub.status_code in (302, 303)
    assert "status=done" in sub.headers["location"]

    # suppressed EVERYWHERE after opt-out
    with Session(lv.engine) as s:
        lead = s.get(Lead, lead_id)
        u = s.get(User, u_id)
        assert s.exec(select(OptOutRequest).where(
            OptOutRequest.value == "optme.com",
            OptOutRequest.applied == True)).first() is not None  # noqa: E712
        assert lead_opted_out(s, lead) is True                       # single source
        assert search(s, ba_id, f) == []                            # search + preview
        with pytest.raises(LeadSuppressed):
            unlock_lead(s, u, lead_id)                               # unlock
        s.add(PurchasedLead(buyer_account_id=ba_id, lead_id=lead_id)); s.commit()
        assert "OptMe Ltd" not in export_purchased_csv(s, u).decode("utf-8")  # export
