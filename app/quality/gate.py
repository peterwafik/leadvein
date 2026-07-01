from __future__ import annotations

from app.core.targeting.view import get_path, MISSING
from app.quality.tiers import meets


def _tier(view: dict, field: str) -> str:
    t = get_path(view, f"validation.{field}.tier")
    return "absent" if t is MISSING else t


def _field_meets(view: dict, field: str, required: str) -> bool:
    if field == "business_contact":   # phone OR email at the required tier
        return meets(_tier(view, "phone"), required) or meets(_tier(view, "email"), required)
    return meets(_tier(view, field), required)


def clears_gate(view: dict, profile) -> bool:
    return all(_field_meets(view, f, req) for f, req in profile.required.items())


def profile_score(view: dict, profile) -> int:
    weights = profile.weights or {}
    total = sum(weights.values()) or 1
    got = sum(w for f, w in weights.items() if _field_meets(view, f, "validated"))
    return round(got / total * 100)
