from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.compliance import is_suppressed, is_opted_out, host_of, audit
from app.core.db import (BuyerAccount, Lead, PurchasedLead, CreditTransaction, _now)
from app.core.serve_filters import passes_serve_filters


class InsufficientCredits(ValueError):
    pass


class LeadSuppressed(ValueError):
    pass


class ComplianceNotAcknowledged(ValueError):
    pass


class LeadHeldBack(ValueError):
    pass


def _existing_purchase(session, buyer_account_id, lead_id):
    return session.exec(select(PurchasedLead).where(
        PurchasedLead.buyer_account_id == buyer_account_id,
        PurchasedLead.lead_id == lead_id)).first()


def grant_credits(session: Session, buyer_account_id: int, amount: int,
                  reason: str = "grant", ref: str = "") -> None:
    ba = session.get(BuyerAccount, buyer_account_id)
    ba.credits += amount
    session.add(ba)
    session.add(CreditTransaction(buyer_account_id=buyer_account_id, delta=amount,
                                  reason=reason, ref=ref))
    session.commit()


def balance(session: Session, buyer_account_id: int) -> int:
    ba = session.get(BuyerAccount, buyer_account_id)
    return ba.credits if ba else 0


def unlock_lead(session: Session, user, lead_id: int) -> PurchasedLead:
    ba = session.get(BuyerAccount, user.buyer_account_id)
    if not ba or not ba.compliance_ack_at:
        raise ComplianceNotAcknowledged("compliance acknowledgement required")
    existing = _existing_purchase(session, ba.id, lead_id)
    if existing:
        return existing  # idempotent re-buy, no charge (owned even if credits now low)
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise ValueError("lead not found")
    if (is_opted_out(session, domain=host_of(lead.website_url), phone=lead.phone,
                     email=lead.public_email)
            or is_suppressed(session, ba.id, domain=host_of(lead.website_url),
                             phone=lead.phone, email=lead.public_email,
                             business_name=lead.business_name)):
        raise LeadSuppressed("lead is suppressed or opted out")
    if not passes_serve_filters(session, ba.id, lead):
        raise LeadHeldBack("lead does not meet the quality gate")
    price = lead.price_credits
    if ba.credits < price:
        raise InsufficientCredits(f"need {price}, have {ba.credits}")
    ba.credits -= price
    session.add(ba)
    session.add(CreditTransaction(buyer_account_id=ba.id, delta=-price,
                                  reason="unlock", ref=f"lead:{lead_id}"))
    lead.times_sold += 1
    lead.last_sold_at = _now()
    session.add(lead)
    purchase = PurchasedLead(buyer_account_id=ba.id, lead_id=lead_id, price_credits=price)
    session.add(purchase)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()  # undoes the debit + credit-txn + times_sold
        return session.exec(select(PurchasedLead).where(
            PurchasedLead.buyer_account_id == ba.id,
            PurchasedLead.lead_id == lead_id)).first()
    session.refresh(purchase)
    audit(session, user.id, "unlock", "Lead", str(lead_id),
          {"price": price, "buyer_account_id": ba.id})
    return purchase
