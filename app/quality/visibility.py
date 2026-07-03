from __future__ import annotations

import json

from app.core.db import Lead

# Per-field tiers surfaced to buyers. Tiers only — never contact values.
# The quality layer MAY import core; core must never import this (INV-Q5).
_TIER_FIELDS = ("phone", "email", "address", "website", "profile")


def quality_summary(lead: Lead) -> dict:
    """Per-field validation tiers for display. Tiers only — never contact values.
    Self-run validation caps at 'validated'; verified_live only arrives via a
    licensed-source stamp, so passing tiers through cannot overclaim."""
    v = json.loads(lead.validation_json or "{}")
    out = {}
    for f in _TIER_FIELDS:
        fb = v.get(f) or {}
        entry = {"tier": fb.get("tier", "absent")}
        if f == "phone" and fb.get("line_type"):
            entry["line_type"] = fb["line_type"]
        out[f] = entry
    return out


def tech_match(lead: Lead) -> dict | None:
    """Fingerprint match summary from stored attributes — key + signal strength."""
    attrs = json.loads(lead.attributes_json or "{}")
    if attrs.get("recipe_key"):
        return {"recipe_key": attrs["recipe_key"],
                "strength": int(attrs.get("match_strength") or 1)}
    return None


def with_quality(view: dict, lead: Lead) -> dict:
    """Enrich a core view dict (mask_preview / unlock_view) with quality tiers
    and tech-match, at the web layer. Keeps core free of quality concepts."""
    return {**view, "quality": quality_summary(lead), "tech_match": tech_match(lead)}
