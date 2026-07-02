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

    Budget/usage fields (used, remaining) are populated from SourceBudget when a
    *session* is provided; otherwise both default to 0.
    """
    from app.adapters.budget import remaining as _remaining
    result = []
    for adapter in _ADAPTERS.values():
        meta = adapter.meta
        cap: int = meta.free_tier.get("cap", 0) if meta.free_tier else 0
        if session is not None and cap > 0:
            rem = _remaining(session, meta.key, cap)
            used = cap - rem
        else:
            rem = 0
            used = 0
        result.append({
            "key": meta.key,
            "name": meta.name,
            "type": meta.type,
            "enabled": enabled(adapter),
            "terms_status": meta.terms_status,
            "free_tier": meta.free_tier,
            "used": used,
            "remaining": rem,
        })
    return result
