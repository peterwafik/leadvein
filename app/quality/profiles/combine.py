"""Honest intersection of quality profiles: every requirement from every profile
is kept, at the highest tier any profile demands. Nothing is silently overridden."""
from __future__ import annotations

from app.quality.profiles.base import QualityProfile
from app.quality.tiers import TIER_ORDER


def combine_profiles(profiles: list[QualityProfile]) -> QualityProfile:
    profiles = [p for p in profiles if p is not None]
    if not profiles:
        raise ValueError("combine_profiles requires at least one profile")
    if len(profiles) == 1:
        return profiles[0]
    required: dict[str, str] = {}
    weights: dict[str, int] = {}
    for p in profiles:
        for field_, tier in p.required.items():
            cur = required.get(field_)
            if cur is None or TIER_ORDER.index(tier) > TIER_ORDER.index(cur):
                required[field_] = tier
        # weights merge takes max, mirroring required-tier merging
        for f, w in p.weights.items():
            weights[f] = max(weights.get(f, 0), w)
    return QualityProfile(
        key="+".join(p.key for p in profiles) or "none",
        label=" + ".join(p.label for p in profiles),
        required=required, weights=weights)
