"""SQL pre-narrowing clauses for quality profiles (spec §3).

Superset filter ONLY: the Python gate (clears_gate) remains the serve
authority on every lead (INV-Q1). Returns None when a profile requires a
field the tier columns don't cover — callers then skip SQL narrowing."""
from __future__ import annotations

from app.core.db import Lead
from app.quality.ordinals import FIELDS, ordinal


def profile_clauses(profile) -> list | None:
    clauses = []
    for field_, tier in (profile.required or {}).items():
        if field_ == "business_contact":
            clauses.append(Lead.tier_contact >= ordinal(tier))
        elif field_ in FIELDS:
            clauses.append(getattr(Lead, f"tier_{field_}") >= ordinal(tier))
        else:
            return None
    return clauses
