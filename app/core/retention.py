from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.core.db import Lead, LeadCategoryLink, PurchasedLead

RETENTION_DAYS = 365


def expiry_for(date_last_verified: str | None) -> str | None:
    if not date_last_verified:
        return None
    try:
        dt = datetime.fromisoformat(date_last_verified)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt + timedelta(days=RETENTION_DAYS)).isoformat()


def is_expired(lead, now_iso: str | None = None) -> bool:
    if not lead.retention_expiry:
        return False
    now = now_iso or datetime.now(timezone.utc).isoformat()
    return lead.retention_expiry < now


def expired_count(session: Session) -> int:
    now = datetime.now(timezone.utc).isoformat()
    return len([l for l in session.exec(select(Lead)).all() if is_expired(l, now)])


def purge_expired(session: Session) -> int:
    """Delete expired UNSOLD leads + their category links. Sold leads are retained
    (a buyer's purchase + audit trail must not be orphaned). Returns count removed."""
    now = datetime.now(timezone.utc).isoformat()
    removed = 0
    for lead in session.exec(select(Lead)).all():
        if not is_expired(lead, now):
            continue
        sold = session.exec(select(PurchasedLead).where(
            PurchasedLead.lead_id == lead.id)).first()
        if sold:
            continue
        for link in session.exec(select(LeadCategoryLink).where(
                LeadCategoryLink.lead_id == lead.id)).all():
            session.delete(link)
        session.delete(lead)
        removed += 1
    session.commit()
    return removed
