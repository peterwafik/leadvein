from __future__ import annotations

from app.scoring.profiles.base import ScoringProfile

_PROFILES: dict[str, ScoringProfile] = {}


def register(profile: ScoringProfile) -> None:
    _PROFILES[profile.key] = profile


def get(key: str) -> ScoringProfile:
    if key not in _PROFILES:
        raise KeyError(f"no scoring profile '{key}'")
    return _PROFILES[key]


def all_keys() -> list[str]:
    return sorted(_PROFILES.keys())
