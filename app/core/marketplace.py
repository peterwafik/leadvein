from __future__ import annotations

from sqlmodel import Session

from app.core.compliance import is_suppressed, is_opted_out, host_of
from app.core.masking import mask_preview, is_owned
from app.core.recipes import matching_leads


def _not_suppressed(session: Session, buyer_account_id: int, lead) -> bool:
    return not is_suppressed(session, buyer_account_id,
                             domain=host_of(lead.website_url), phone=lead.phone,
                             email=lead.public_email,
                             business_name=lead.business_name)


def search(session: Session, buyer_account_id: int, filters: dict) -> list[dict]:
    leads = matching_leads(session, filters)
    out = []
    for l in leads:
        if not _not_suppressed(session, buyer_account_id, l):
            continue
        if is_opted_out(session, domain=host_of(l.website_url), phone=l.phone, email=l.public_email):
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
