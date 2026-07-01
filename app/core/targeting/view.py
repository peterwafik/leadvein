from __future__ import annotations

import json

_MISSING = object()
MISSING = _MISSING  # sentinel: path absent (distinct from a stored None/False)


def _load(blob: str) -> dict:
    try:
        return json.loads(blob or "{}") or {}
    except (ValueError, TypeError):
        return {}


def lead_view(lead) -> dict:
    return {
        "id": lead.id, "business_name": lead.business_name,
        "category_keys": json.loads(lead.category_keys_json or "[]"),
        "city": lead.city, "region": lead.region, "country": lead.country,
        "postal_code": lead.postal_code, "latitude": lead.latitude, "longitude": lead.longitude,
        "phone": lead.phone, "public_email": lead.public_email, "website_url": lead.website_url,
        "opening_hours": getattr(lead, "opening_hours", ""),
        "validation": _load(lead.validation_json), "quality_score": lead.quality_score,
        "score_total": lead.score_total, "subscores": _load(lead.subscores_json),
        "attributes": _load(lead.attributes_json), "intent": _load(lead.intent_json),
        "source_key": lead.source_key, "source_license": lead.source_license,
        "scoring_profile_key": lead.scoring_profile_key,
        "date_discovered": lead.date_discovered, "date_last_verified": lead.date_last_verified,
        "retention_expiry": lead.retention_expiry, "times_sold": lead.times_sold,
    }


def get_path(view: dict, path: str):
    cur = view
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return MISSING
    return cur
