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


def test_gateway_is_enabled_reflects_env(monkeypatch):
    from app.billing import stripe_gateway
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    assert stripe_gateway.is_enabled() is False
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    assert stripe_gateway.is_enabled() is True


def test_fulfill_grants_once_and_is_idempotent():
    from sqlmodel import Session, select
    from app.core.db import init_db, BuyerAccount, CreditTransaction
    from app.core.purchasing import balance
    from app.billing.service import fulfill_session
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba = BuyerAccount(company_name="A", credits=0); s.add(ba); s.commit(); s.refresh(ba)
        p1 = fulfill_session(s, "cs_1", ba.id, 100, "pack_100", 2900, "gbp")
        assert p1.status == "completed"
        assert balance(s, ba.id) == 100
        # replay (webhook retry) — must NOT double-credit
        p2 = fulfill_session(s, "cs_1", ba.id, 100)
        assert p2.id == p1.id
        assert balance(s, ba.id) == 100
        # exactly one credit ledger row for this session
        txns = s.exec(select(CreditTransaction).where(
            CreditTransaction.ref == "cs_1")).all()
        assert len(txns) == 1


def test_record_pending_creates_pending_row():
    from sqlmodel import Session
    from app.core.db import init_db, StripePayment
    from app.billing.service import record_pending
    engine = init_db("sqlite://")
    with Session(engine) as s:
        p = record_pending(s, "cs_2", 7, "pack_500", 500, 11900, "gbp")
        assert p.status == "pending" and p.buyer_account_id == 7
