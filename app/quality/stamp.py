from __future__ import annotations

from app.quality.tiers import achieved_tier
from app.quality.validators.email import validate_email, _default_mx
from app.quality.validators.phone import validate_phone
from app.quality.validators.address import validate_address
from app.quality.validators.website import validate_website
from app.quality.validators.profile import validate_profile
from app.quality.validators.freshness import validate_freshness

DEFAULT_WEIGHTS = {"email": 25, "phone": 25, "address": 15, "website": 10,
                   "profile": 15, "freshness": 10}


def build_validation(fields: dict, *, mx_lookup=None) -> dict:
    addr = fields.get("address") or {}
    blobs = {
        "email": validate_email(fields.get("email", ""), mx_lookup=mx_lookup or _default_mx),
        "phone": validate_phone(fields.get("phone", "")),
        "address": validate_address(addr.get("line1", ""), addr.get("city", ""),
                                    addr.get("postal_code", ""), addr.get("country", ""),
                                    addr.get("lat"), addr.get("lon")),
        "website": validate_website(fields.get("intent") or {}),
        "profile": validate_profile(fields.get("name", ""), fields.get("category_keys"),
                                    fields.get("city", ""), fields.get("opening_hours", ""),
                                    fields.get("website_url", "")),
        "freshness": validate_freshness(fields.get("date_last_verified")),
    }
    for fb in blobs.values():
        fb["tier"] = achieved_tier(fb)
    # NOTE (INV-Q2/Q6): no gated field (has_mca/amount_owed/lender/size_band) is produced here,
    # and no verified_live tier is ever self-generated — that requires a licensed provider.
    return blobs


def quality_score(validation: dict, weights: dict = None) -> int:
    weights = weights or DEFAULT_WEIGHTS
    total = sum(weights.values()) or 1
    got = sum(w for k, w in weights.items()
              if (validation.get(k) or {}).get("tier") in ("validated", "verified_live"))
    return round(got / total * 100)
