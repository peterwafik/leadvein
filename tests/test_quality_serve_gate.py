import json
import pytest
from sqlmodel import Session
from app.core.db import init_db, Lead, BuyerAccount, User, _now
from app.core.leadcats import sync_lead_categories
from app.core.marketplace import search
from app.core.recipes import DEFAULT_FILTERS
from app.core.targeting import registry as targeting_registry
from app.core.targeting.estimate import estimate
from app.core.purchasing import unlock_lead, grant_credits, LeadHeldBack
from app.core.serve_filters import clear as clear_filters
from app.quality.runtime import register_quality_runtime
from app.quality.profiles.baseline import BASELINE
from app.quality.serve_gate import set_gate_profile
from app.targeting.runtime import register_targeting_runtime


def _lead(session, validation):
    lead = Lead(business_name="Maybe Hot", category_keys_json=json.dumps(["cafe"]),
                city="London", phone="1", public_email="info@x.com", website_url="https://x.com",
                score_total=90, date_last_verified=_now(), price_credits=3,
                validation_json=json.dumps(validation))
    session.add(lead); session.commit(); session.refresh(lead)
    sync_lead_categories(session, lead)
    return lead


def _buyer(session):
    ba = BuyerAccount(company_name="B", credits=0, compliance_ack_at=_now())
    session.add(ba); session.commit(); session.refresh(ba)
    u = User(email="b@b.com", password_hash="x", role="buyer", buyer_account_id=ba.id)
    session.add(u); session.commit(); session.refresh(u)
    grant_credits(session, ba.id, 50)
    return ba, u


def _setup():
    # Ensure targeting predicates are registered (needed for estimate's matching_by_composition)
    register_targeting_runtime()
    clear_filters(); register_quality_runtime(); set_gate_profile(BASELINE)


def test_incomplete_lead_held_back_at_search_preview_and_unlock():   # INV-Q1 (all three)
    _setup()
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u = _buyer(s)
        # contact only "present" (not validated) -> below baseline -> HOT bar not met
        cold = _lead(s, {"profile": {"tier": "validated"},
                         "email": {"tier": "present"}, "phone": {"tier": "present"}})
        f = {**DEFAULT_FILTERS, "categories": ["cafe"], "city": "London"}
        # 1) SEARCH: not surfaced
        assert search(s, ba.id, f) == []
        # 2) PREVIEW/ESTIMATE: not counted, no sample
        comp = {"op": "AND", "nodes": [{"predicate": "geo.city", "params": {"value": "London"}}]}
        est = estimate(s, ba.id, comp)
        assert est["count"] == 0 and est["samples"] == []
        # 3) UNLOCK: refused
        with pytest.raises(LeadHeldBack):
            unlock_lead(s, u, cold.id)


def test_hot_lead_passes_all_three():
    _setup()
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u = _buyer(s)
        hot = _lead(s, {"profile": {"tier": "validated"},
                        "email": {"tier": "validated"}, "phone": {"tier": "validated"}})
        f = {**DEFAULT_FILTERS, "categories": ["cafe"], "city": "London"}
        assert len(search(s, ba.id, f)) == 1
        comp = {"op": "AND", "nodes": [{"predicate": "geo.city", "params": {"value": "London"}}]}
        assert estimate(s, ba.id, comp)["count"] == 1
        assert unlock_lead(s, u, hot.id) is not None


def test_gate_is_load_bearing_not_noop():
    """GUARD: proves gate-on vs gate-off makes a real difference.

    With clear() (gate OFF) a blob-less lead SURFACES in search and is unlockable.
    After register_quality_runtime() + set_gate_profile(BASELINE) (gate ON) the SAME
    kind of lead is held back at search AND unlock_lead raises LeadHeldBack.
    This test FAILS if passes_serve_filters always returns True, or if the unlock
    wiring is removed, or if the gate is globally disabled/no-op'd.
    """
    # --- Gate OFF ---
    clear_filters()
    engine_off = init_db("sqlite://")
    with Session(engine_off) as s:
        ba, u = _buyer(s)
        lead_off = _lead(s, {})  # no validation blob -> would fail gate when ON
        f = {**DEFAULT_FILTERS, "categories": ["cafe"], "city": "London"}
        results_off = search(s, ba.id, f)
        assert len(results_off) == 1, (
            "Gate OFF: a blob-less lead must surface in search "
            "(if this fails, something else is blocking the lead)"
        )
        purchase_off = unlock_lead(s, u, lead_off.id)
        assert purchase_off is not None, (
            "Gate OFF: a blob-less lead must be unlockable"
        )

    # --- Gate ON ---
    clear_filters(); register_quality_runtime(); set_gate_profile(BASELINE)
    engine_on = init_db("sqlite://")
    with Session(engine_on) as s:
        ba, u = _buyer(s)
        lead_on = _lead(s, {})  # same: no validation blob
        f = {**DEFAULT_FILTERS, "categories": ["cafe"], "city": "London"}
        results_on = search(s, ba.id, f)
        assert results_on == [], (
            "Gate ON: a blob-less lead must NOT surface in search "
            "(if this fails, passes_serve_filters is not wired into search)"
        )
        with pytest.raises(LeadHeldBack, match="quality gate"):
            unlock_lead(s, u, lead_on.id)
