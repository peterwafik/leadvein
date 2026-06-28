from __future__ import annotations

import json

from sqlmodel import Session, select, delete

from app.core.db import LeadCategoryLink


def sync_lead_categories(session: Session, lead) -> None:
    """(Re)build the normalized category links for a lead from its category_keys_json."""
    session.exec(delete(LeadCategoryLink).where(LeadCategoryLink.lead_id == lead.id))
    for key in json.loads(lead.category_keys_json or "[]"):
        session.add(LeadCategoryLink(lead_id=lead.id, category_key=key))
    session.commit()


def lead_ids_for_categories(session: Session, category_keys) -> set:
    """Lead ids that have ANY of the given category keys (via the indexed link table)."""
    keys = [k for k in (category_keys or []) if k]
    if not keys:
        return set()
    rows = session.exec(select(LeadCategoryLink.lead_id).where(
        LeadCategoryLink.category_key.in_(keys))).all()
    return set(rows)
