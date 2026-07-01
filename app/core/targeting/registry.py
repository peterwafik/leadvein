from __future__ import annotations

_PREDS: dict = {}


def register(predicate) -> None:
    _PREDS[predicate.key] = predicate


def get(key: str):
    if key not in _PREDS:
        raise KeyError(f"no predicate '{key}'")
    return _PREDS[key]


def all_keys() -> list[str]:
    return sorted(_PREDS.keys())


def available(populated_paths: set) -> list:
    return [p for p in _PREDS.values() if set(p.reads) <= set(populated_paths)]


def clear() -> None:
    _PREDS.clear()
