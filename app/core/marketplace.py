from __future__ import annotations

from sqlmodel import Session, select

from app.core.compliance import (is_suppressed, host_of, lead_opted_out, _norm)
from app.core.db import SuppressionList, SuppressionEntry
from app.core.retention import is_expired
from app.core.masking import mask_preview, is_owned
from app.core.recipes import matching_leads
from app.core.serve_filters import passes_serve_filters


def _not_suppressed(session: Session, buyer_account_id: int, lead) -> bool:
    return not is_suppressed(session, buyer_account_id,
                             domain=host_of(lead.website_url), phone=lead.phone,
                             email=lead.public_email,
                             business_name=lead.business_name)


# Kinds a SuppressionEntry can carry (mirrors the checks in is_suppressed).
_SUPPRESSION_KINDS = ("domain", "phone", "email", "business_name")


class SuppressionIndex:
    """In-memory snapshot of a buyer's applicable suppression entries (global +
    buyer-owned lists), keyed by kind -> set of normalized values.

    Built once (two queries), then matched against many leads with zero further
    DB round-trips. `.not_suppressed(lead)` is equivalent to
    `_not_suppressed(session, buyer_account_id, lead)`: same lists (global +
    this buyer), same kinds, same `_norm` normalization, same
    "no list => nothing suppressed" and "any matching field suppresses" rules.
    """

    def __init__(self, by_kind: dict[str, set[str]]):
        self._by_kind = by_kind

    def is_suppressed(self, lead) -> bool:
        checks = [("domain", host_of(lead.website_url)), ("phone", lead.phone),
                  ("email", lead.public_email),
                  ("business_name", lead.business_name)]
        for kind, value in checks:
            if not value:
                continue
            if _norm(kind, value) in self._by_kind[kind]:
                return True
        return False

    def not_suppressed(self, lead) -> bool:
        return not self.is_suppressed(lead)


def build_suppression_index(session: Session,
                            buyer_account_id: int | None) -> SuppressionIndex:
    """Load the buyer's applicable suppression entries once (batch prefetch)."""
    by_kind: dict[str, set[str]] = {k: set() for k in _SUPPRESSION_KINDS}
    lists = session.exec(select(SuppressionList).where(
        (SuppressionList.buyer_account_id == None)  # noqa: E711  (global)
        | (SuppressionList.buyer_account_id == buyer_account_id))).all()
    list_ids = [l.id for l in lists]
    if list_ids:
        entries = session.exec(select(SuppressionEntry).where(
            SuppressionEntry.list_id.in_(list_ids))).all()
        for e in entries:
            if e.kind in by_kind:
                by_kind[e.kind].add(_norm(e.kind, e.value))
    return SuppressionIndex(by_kind)


def search(session: Session, buyer_account_id: int, filters: dict) -> list[dict]:
    leads = matching_leads(session, filters)
    out = []
    for l in leads:
        if is_expired(l):
            continue
        if not _not_suppressed(session, buyer_account_id, l):
            continue
        if lead_opted_out(session, l):
            continue
        if not passes_serve_filters(session, buyer_account_id, l):
            continue
        preview = mask_preview(l)
        preview["already_owned"] = is_owned(session, buyer_account_id, l.id)
        out.append(preview)
    return out


def estimate(session: Session, buyer_account_id: int, filters: dict) -> dict:
    previews = search(session, buyer_account_id, filters)
    buckets = {"80+": 0, "50-79": 0, "<50": 0}
    for p in previews:
        s = p["score_total"]
        buckets["80+" if s >= 80 else "50-79" if s >= 50 else "<50"] += 1
    return {"count": len(previews), "score_buckets": buckets,
            "sample": previews[:10],
            "total_price_credits": sum(p["price_credits"] for p in previews)}
