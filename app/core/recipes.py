from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.db import Lead
from app.core.leadcats import lead_ids_for_categories

DEFAULT_FILTERS = {
    "categories": [], "city": "", "region": "", "country": "",
    "require_phone": False, "require_email": False, "require_website": False,
    "freshness_days": 0, "min_score": 0, "exclude_categories": [],
}


def _days_since(iso: str | None) -> float:
    if not iso:
        return 9999.0
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return 9999.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0


def matching_leads(session: Session, filters: dict, *,
                   exclude_lead_ids: set = frozenset()) -> list[Lead]:
    f = {**DEFAULT_FILTERS, **(filters or {})}
    rows = session.exec(select(Lead).where(
        Lead.score_total >= int(f["min_score"]))).all()
    cats = [c for c in (f["categories"] or []) if c]
    excl = set(f["exclude_categories"] or [])
    cat_ids = lead_ids_for_categories(session, cats) if cats else None  # None = no category filter
    out = []
    for l in rows:
        if l.id in exclude_lead_ids:
            continue
        if cat_ids is not None and l.id not in cat_ids:
            continue
        if excl and (set(json.loads(l.category_keys_json or "[]")) & excl):
            continue
        if f["city"] and f["city"].lower() not in (l.city or "").lower():
            continue
        if f["region"] and f["region"].lower() not in (l.region or "").lower():
            continue
        if f["country"] and f["country"].lower() not in (l.country or "").lower():
            continue
        if f["require_phone"] and not l.phone:
            continue
        if f["require_email"] and not l.public_email:
            continue
        if f["require_website"] and not l.website_url:
            continue
        if int(f["freshness_days"]) > 0 and _days_since(l.date_last_verified) > int(f["freshness_days"]):
            continue
        out.append(l)
    return out
