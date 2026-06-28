from __future__ import annotations

import re

from sqlmodel import Session, select

from app.adapters.base import NormalizedLead
from app.core.compliance import host_of
from app.core.db import Lead


def _slug(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]+", "", s)  # Remove punctuation, keep spaces
    return re.sub(r"\s+", "-", s).strip("-")  # Replace spaces with hyphens


def dedupe_key(lead: NormalizedLead) -> str:
    if lead.website_url:
        host = host_of(lead.website_url)
        if host:
            return f"domain:{host}"
    if lead.phone:
        digits = re.sub(r"\D", "", lead.phone)
        if digits:
            return f"phone:{digits}"
    city = (lead.address or {}).get("city", "")
    return f"name:{_slug(lead.business_name)}|{_slug(city)}"


def find_existing(session: Session, key: str) -> Lead | None:
    if not key:
        return None
    return session.exec(select(Lead).where(Lead.dedupe_key == key)).first()
