import pytest
from sqlmodel import Session, select
from app.core.db import (init_db, BuyerAccount, User, Lead, PurchasedLead,
                         CreditTransaction, OptOutRequest, _now)
from app.core.purchasing import (grant_credits, balance, unlock_lead,
                                 InsufficientCredits, LeadSuppressed,
                                 ComplianceNotAcknowledged)


def _setup(s, credits=10, acked=True):
    ba = BuyerAccount(company_name="Acme", credits=0,
                      compliance_ack_at=_now() if acked else None)
    s.add(ba); s.commit(); s.refresh(ba)
    u = User(email="a@b.com", password_hash="x", role="buyer", buyer_account_id=ba.id)
    s.add(u); s.commit(); s.refresh(u)
    if credits:
        grant_credits(s, ba.id, credits)
    lead = Lead(business_name="D", website_url="https://d.com", phone="1",
                price_credits=3, date_last_verified=_now())
    s.add(lead); s.commit(); s.refresh(lead)
    return ba, u, lead


def test_unlock_debits_and_creates_purchase():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u, lead = _setup(s)
        p = unlock_lead(s, u, lead.id)
        assert isinstance(p, PurchasedLead)
        assert balance(s, ba.id) == 7
        assert s.get(Lead, lead.id).times_sold == 1


def test_rebuy_is_idempotent_no_double_charge():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u, lead = _setup(s)
        first = unlock_lead(s, u, lead.id)
        again = unlock_lead(s, u, lead.id)
        assert again.id == first.id
        assert balance(s, ba.id) == 7   # charged once


def test_insufficient_credits_blocked():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u, lead = _setup(s, credits=1)
        with pytest.raises(InsufficientCredits):
            unlock_lead(s, u, lead.id)


def test_compliance_ack_required():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u, lead = _setup(s, acked=False)
        with pytest.raises(ComplianceNotAcknowledged):
            unlock_lead(s, u, lead.id)


def test_suppressed_or_optout_blocked():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u, lead = _setup(s)
        s.add(OptOutRequest(kind="domain", value="d.com", applied=True))
        s.commit()
        with pytest.raises(LeadSuppressed):
            unlock_lead(s, u, lead.id)
