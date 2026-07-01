from __future__ import annotations

TIER_ORDER = ["absent", "present", "validated", "verified_live"]


def achieved_tier(fb: dict) -> str:
    if not fb or not fb.get("present"):
        return "absent"
    if fb.get("verified_live"):
        return "verified_live"
    if fb.get("validated"):
        return "validated"
    return "present"


def meets(achieved: str, required: str) -> bool:
    return TIER_ORDER.index(achieved) >= TIER_ORDER.index(required)
