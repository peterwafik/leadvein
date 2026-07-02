from __future__ import annotations

import os

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


def enabled(adapter) -> bool:
    """Return True when the adapter's required API key is present in env.

    An adapter with key_env=="" requires no key and is always enabled.
    Keys are read exclusively from the process environment; never from files.
    """
    key_env = adapter.meta.key_env
    return key_env == "" or bool(os.getenv(key_env))


def list_status(session=None) -> list[dict]:
    """Return a status dict for every registered adapter.

    Budget/usage fields (used, remaining) are reserved for a later task and
    default to 0 here so callers can rely on the keys existing.
    """
    result = []
    for adapter in _ADAPTERS.values():
        meta = adapter.meta
        result.append({
            "key": meta.key,
            "name": meta.name,
            "type": meta.type,
            "enabled": enabled(adapter),
            "terms_status": meta.terms_status,
            "free_tier": meta.free_tier,
            "used": 0,
            "remaining": 0,
        })
    return result
