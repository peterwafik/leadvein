"""Tests for the US outreach hold-gate (DNC/TCPA).

INV-US1: US-region leads are held at search, estimate, and unlock until a
DNC/TCPA clearance flag is present.  GB (and other non-US) leads are unaffected.
"""
from __future__ import annotations

import json

import pytest
from sqlmodel import Session

from app.compliance.outreach_gate import compliance_region, register_outreach_gate
from app.core.db import init_db, Lead, BuyerAccount, User, _now
from app.core.leadcats import sync_lead_categories
from app.core.marketplace import search
from app.core.purchasing import grant_credits, unlock_lead, LeadHeldBack
from app.core.recipes import DEFAULT_FILTERS
from app.core.serve_filters import clear as clear_filters
from app.core.targeting.estimate import estimate
from app.quality.profiles.baseline import BASELINE
from app.quality.runtime import register_quality_runtime
from app.quality.serve_gate import set_gate_profile
from app.targeting.runtime import register_targeting_runtime
from tests.quality_helpers import hot_validation_json


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _setup():
    """Register both gates exactly as production startup does."""
    register_targeting_runtime()
    clear_filters()
    register_quality_runtime()
    set_gate_profile(BASELINE)
    register_outreach_gate()


def _hot_lead(session: Session, country: str) -> Lead:
    """Seed a HOT lead (passes quality gate) with the given country."""
    lead = Lead(
        business_name=f"HotBiz-{country}",
        category_keys_json=json.dumps(["cafe"]),
        city="Testville",
        phone="1",
        public_email=f"info@biz-{country.lower()}.example",
        website_url=f"https://biz-{country.lower()}.example",
        score_total=90,
        date_last_verified=_now(),
        price_credits=2,
        country=country,
        validation_json=hot_validation_json(),
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    sync_lead_categories(session, lead)
    return lead


def _buyer(session: Session):
    ba = BuyerAccount(company_name="Buyer", credits=0, compliance_ack_at=_now())
    session.add(ba)
    session.commit()
    session.refresh(ba)
    u = User(email="buyer@us-hold.local", password_hash="x",
             role="buyer", buyer_account_id=ba.id)
    session.add(u)
    session.commit()
    session.refresh(u)
    grant_credits(session, ba.id, 50)
    return ba, u


# ---------------------------------------------------------------------------
# Unit tests: compliance_region()
# ---------------------------------------------------------------------------

def test_compliance_region_us():
    assert compliance_region("US") == "US"


def test_compliance_region_usa():
    assert compliance_region("USA") == "US"


def test_compliance_region_us_lowercase():
    assert compliance_region("us") == "US"


def test_compliance_region_gb():
    assert compliance_region("GB") == "GB"


def test_compliance_region_empty():
    assert compliance_region("") == ""


def test_compliance_region_other():
    assert compliance_region("DE") == "DE"


# ---------------------------------------------------------------------------
# INV-US1: US lead held; GB lead serves normally (search / estimate / unlock)
# ---------------------------------------------------------------------------

def test_us_lead_absent_from_search():   # INV-US1 — search
    _setup()
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, _ = _buyer(s)
        _hot_lead(s, "US")
        f = {**DEFAULT_FILTERS, "categories": ["cafe"], "city": "Testville"}
        results = search(s, ba.id, f)
        assert results == [], "US lead must be held back from search"


def test_us_lead_absent_from_estimate():   # INV-US1 — estimate / composer preview
    _setup()
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, _ = _buyer(s)
        _hot_lead(s, "US")
        comp = {"op": "AND", "nodes": [
            {"predicate": "geo.city", "params": {"value": "Testville"}}
        ]}
        est = estimate(s, ba.id, comp)
        assert est["count"] == 0, "US lead must not appear in composer estimate"
        assert est["samples"] == [], "US lead must not appear in composer samples"


def test_us_lead_unlock_raises_held_back():   # INV-US1 — unlock
    _setup()
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u = _buyer(s)
        us_lead = _hot_lead(s, "US")
        with pytest.raises(LeadHeldBack):
            unlock_lead(s, u, us_lead.id)


def test_gb_lead_serves_normally_search():   # control group — search
    _setup()
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, _ = _buyer(s)
        _hot_lead(s, "GB")
        f = {**DEFAULT_FILTERS, "categories": ["cafe"], "city": "Testville"}
        results = search(s, ba.id, f)
        assert len(results) == 1, "GB lead must pass through the outreach gate"


def test_gb_lead_serves_normally_estimate():   # control group — estimate
    _setup()
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, _ = _buyer(s)
        _hot_lead(s, "GB")
        comp = {"op": "AND", "nodes": [
            {"predicate": "geo.city", "params": {"value": "Testville"}}
        ]}
        est = estimate(s, ba.id, comp)
        assert est["count"] == 1, "GB lead must appear in composer estimate"


def test_gb_lead_unlockable():   # control group — unlock
    _setup()
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u = _buyer(s)
        gb_lead = _hot_lead(s, "GB")
        purchase = unlock_lead(s, u, gb_lead.id)
        assert purchase is not None, "GB lead must be unlockable"


def test_only_gb_lead_surfaces_when_both_seeded():   # INV-US1 — mixed DB
    """Both a US and a GB HOT lead exist; only the GB lead must be visible."""
    _setup()
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, _ = _buyer(s)
        _hot_lead(s, "US")
        _hot_lead(s, "GB")
        f = {**DEFAULT_FILTERS, "categories": ["cafe"], "city": "Testville"}
        results = search(s, ba.id, f)
        assert len(results) == 1
        assert results[0]["country"] == "GB"
