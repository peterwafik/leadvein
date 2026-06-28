from __future__ import annotations

from app.adapters.base import LeadSourceAdapter

_ADAPTERS: dict[str, LeadSourceAdapter] = {}


def register(adapter: LeadSourceAdapter) -> None:
    _ADAPTERS[adapter.meta.key] = adapter


def get(key: str) -> LeadSourceAdapter:
    if key not in _ADAPTERS:
        raise KeyError(f"no adapter registered for '{key}'")
    return _ADAPTERS[key]


def all_keys() -> list[str]:
    return sorted(_ADAPTERS.keys())
