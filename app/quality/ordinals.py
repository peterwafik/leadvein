"""Indexed int mirrors of per-field validation tiers.

apply_tier_columns is the ONLY writer of Lead.tier_* columns and must be
called at every site that writes validation_json — single writer, no drift.
The columns exist so estimate/search can PRE-NARROW candidates in SQL at
100k+ rows; the Python gate (clears_gate on the JSON) remains the serve
authority (INV-Q1)."""
from __future__ import annotations

from app.quality.tiers import TIER_ORDER

FIELDS = ("phone", "email", "address", "website", "profile")


def ordinal(tier: str) -> int:
    try:
        return TIER_ORDER.index(tier)
    except ValueError:
        return 0          # unknown tier fails closed


def apply_tier_columns(lead, validation: dict) -> None:
    for f in FIELDS:
        t = ((validation.get(f) or {}).get("tier")) or "absent"
        setattr(lead, f"tier_{f}", ordinal(t))
    lead.tier_contact = max(lead.tier_phone, lead.tier_email)
