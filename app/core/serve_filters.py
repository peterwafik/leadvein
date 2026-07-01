from __future__ import annotations

_FILTERS = []


def register_serve_filter(fn) -> None:
    if fn not in _FILTERS:
        _FILTERS.append(fn)


def passes_serve_filters(session, buyer_account_id, lead) -> bool:
    return all(fn(session, buyer_account_id, lead) for fn in _FILTERS)


def clear() -> None:
    _FILTERS.clear()
