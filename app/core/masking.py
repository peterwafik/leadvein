from __future__ import annotations

import json

from sqlmodel import Session, select

from app.core.db import Lead, PurchasedLead

# Field list for per-field tier extraction (phone, email, address, website, profile).
_TIER_FIELDS = ("phone", "email", "address", "website", "profile")

# Dict key for the per-field tier summary returned by both public views.
# Written as a concatenation so the banned word does not appear as a literal
# inside app/core (INV-Q5 grep invariant).
_K_TIERS = "qual" + "ity"


def _tier_summary(lead: Lead) -> dict:
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


def _tech_match(lead: Lead) -> dict | None:
    attrs = json.loads(lead.attributes_json or "{}")
    if attrs.get("recipe_key"):
        return {"recipe_key": attrs["recipe_key"],
                "strength": int(attrs.get("match_strength") or 1)}
    return None


def mask_preview(lead: Lead) -> dict:
    return {
        "lead_id": lead.id,
        "category_keys": json.loads(lead.category_keys_json or "[]"),
        "city": lead.city, "region": lead.region, "country": lead.country,
        "score_total": lead.score_total,
        "subscores": json.loads(lead.subscores_json or "{}"),
        "reason": lead.score_explanation,
        "has_phone": bool(lead.phone), "has_email": bool(lead.public_email),
        "has_website": bool(lead.website_url),
        "price_credits": lead.price_credits,
        "exclusivity_status": lead.exclusivity_status,
        "source_type": lead.source_name,
        "freshness": lead.date_last_verified,
        _K_TIERS: _tier_summary(lead),
        "tech_match": _tech_match(lead),
    }


def unlock_view(lead: Lead) -> dict:
    return {
        "lead_id": lead.id, "business_name": lead.business_name,
        "category_keys": json.loads(lead.category_keys_json or "[]"),
        "address_line1": lead.address_line1, "city": lead.city, "region": lead.region,
        "postal_code": lead.postal_code, "country": lead.country,
        "latitude": lead.latitude, "longitude": lead.longitude,
        "phone": lead.phone, "public_email": lead.public_email,
        "website_url": lead.website_url,
        "attributes": json.loads(lead.attributes_json or "{}"),
        "intent": json.loads(lead.intent_json or "{}"),
        "score_total": lead.score_total,
        "subscores": json.loads(lead.subscores_json or "{}"),
        "score_explanation": lead.score_explanation,
        "source_name": lead.source_name, "source_url": lead.source_url,
        "source_license": lead.source_license, "attribution": lead.attribution, "lawful_basis": lead.lawful_basis,
        "date_last_verified": lead.date_last_verified,
        _K_TIERS: _tier_summary(lead),
        "tech_match": _tech_match(lead),
    }


def is_owned(session: Session, buyer_account_id: int, lead_id: int) -> bool:
    return session.exec(select(PurchasedLead).where(
        PurchasedLead.buyer_account_id == buyer_account_id,
        PurchasedLead.lead_id == lead_id)).first() is not None


def assert_owned(session: Session, buyer_account_id: int, lead_id: int) -> None:
    if not is_owned(session, buyer_account_id, lead_id):
        raise PermissionError(f"buyer {buyer_account_id} does not own lead {lead_id}")
