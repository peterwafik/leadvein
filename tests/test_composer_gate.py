import json
import re
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session
import app.leadvault as lv
from app.core.db import Lead, BuyerAccount, User, _now, init_db
from app.core.leadcats import sync_lead_categories
from app.core.purchasing import grant_credits, unlock_lead, LeadHeldBack
from tests.quality_helpers import hot_validation_json


def _token_from(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


def _hot(s, city):
    l = Lead(business_name="Hot", category_keys_json=json.dumps(["cafe"]), city=city, phone="1",
             score_total=90, date_last_verified=_now(), price_credits=3,
             validation_json=hot_validation_json())
    s.add(l); s.commit(); s.refresh(l); sync_lead_categories(s, l); return l


def _cold(s, city):  # blob-less -> fails the quality gate
    l = Lead(business_name="Cold", category_keys_json=json.dumps(["cafe"]), city=city, phone="1",
             score_total=90, date_last_verified=_now(), price_credits=3, validation_json="{}")
    s.add(l); s.commit(); s.refresh(l); sync_lead_categories(s, l); return l


def test_cold_lead_unlock_raises_held_back():   # INV-Q1 — unlock gate enforcement on composer-surfaced leads
    """A blob-less (cold) lead that the quality gate holds back must also be rejected by
    unlock_lead — proving the gate applies end-to-end, not just to estimate responses."""
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba = BuyerAccount(company_name="TestBuyer", credits=0, compliance_ack_at=_now())
        s.add(ba); s.commit(); s.refresh(ba)
        grant_credits(s, ba.id, 20)
        u = User(email="buyer@unlock-gate.local", password_hash="x",
                 role="buyer", buyer_account_id=ba.id)
        s.add(u); s.commit(); s.refresh(u)
        cold = _cold(s, "INV_Q1_City")
        with pytest.raises(LeadHeldBack):
            unlock_lead(s, u, cold.id)


def test_composer_estimate_respects_quality_gate():   # INV-Q1 through the composer
    c = TestClient(lv.app)
    # Log in with a valid CSRF token following the pattern in tests/test_csrf.py
    page = c.get("/login").text
    token = _token_from(page)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": token})
    with Session(lv.engine) as s:
        _hot(s, "Composerville"); _cold(s, "Composerville")
    comp = {"op": "AND", "nodes": [{"predicate": "geo.city", "params": {"value": "Composerville"}}]}
    r = c.post("/app/composer/estimate", json={"composition": comp})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1                       # only the HOT lead — cold held back by the gate
    assert "Cold" not in json.dumps(data["samples"]) and "Hot" not in json.dumps(data["samples"])  # masked
