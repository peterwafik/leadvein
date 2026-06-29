from __future__ import annotations

from sqlmodel import Session, select

from app.core.db import StripePayment, _now
from app.core.purchasing import grant_credits


def record_pending(session: Session, session_id: str, buyer_account_id: int,
                   pack_key: str, credits: int, amount_cents: int,
                   currency: str) -> StripePayment:
    pay = StripePayment(session_id=session_id, buyer_account_id=buyer_account_id,
                        pack_key=pack_key, credits=credits, amount_cents=amount_cents,
                        currency=currency, status="pending")
    session.add(pay)
    session.commit()
    session.refresh(pay)
    return pay


def fulfill_session(session: Session, session_id: str, buyer_account_id: int,
                    credits: int, pack_key: str = "", amount_cents: int = 0,
                    currency: str = "gbp") -> StripePayment:
    pay = session.exec(select(StripePayment).where(
        StripePayment.session_id == session_id)).first()
    if pay and pay.status == "completed":
        return pay  # idempotent — already fulfilled (webhook retry/replay)
    if not pay:
        pay = StripePayment(session_id=session_id, buyer_account_id=buyer_account_id,
                            pack_key=pack_key, credits=credits, amount_cents=amount_cents,
                            currency=currency, status="pending")
        session.add(pay)
        session.commit()
        session.refresh(pay)
    pay.status = "completed"
    pay.completed_at = _now()
    session.add(pay)
    grant_credits(session, buyer_account_id, credits, reason="stripe_purchase",
                  ref=session_id)
    session.commit()
    session.refresh(pay)
    return pay
