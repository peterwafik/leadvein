from sqlalchemy.exc import IntegrityError
from sqlmodel import Session
from app.core.db import init_db, StripePayment
from app.billing.packs import get_pack, CREDIT_PACKS, currency


def test_packs_catalog_and_lookup():
    assert get_pack("pack_100").credits == 100
    assert get_pack("pack_1000").amount_cents == 19900
    assert get_pack("nope") is None
    assert {p.key for p in CREDIT_PACKS} == {"pack_100", "pack_500", "pack_1000"}


def test_currency_default_gbp(monkeypatch):
    monkeypatch.delenv("BILLING_CURRENCY", raising=False)
    assert currency() == "gbp"
    monkeypatch.setenv("BILLING_CURRENCY", "USD")
    assert currency() == "usd"


def test_stripe_payment_session_id_is_unique():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        s.add(StripePayment(session_id="cs_1", buyer_account_id=1, credits=100)); s.commit()
        s.add(StripePayment(session_id="cs_1", buyer_account_id=1, credits=100))
        try:
            s.commit()
            raised = False
        except IntegrityError:
            raised = True
        assert raised
