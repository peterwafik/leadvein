from __future__ import annotations

from app.quality.profiles.base import QualityProfile

_PROFILES: dict[str, QualityProfile] = {}


def register(profile: QualityProfile) -> None:
    _PROFILES[profile.key] = profile


def get(key: str) -> QualityProfile:
    if key not in _PROFILES:
        raise KeyError(f"no quality profile '{key}'")
    return _PROFILES[key]


def all_keys() -> list[str]:
    return sorted(_PROFILES.keys())
