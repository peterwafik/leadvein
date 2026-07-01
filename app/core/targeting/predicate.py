from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.targeting.view import MISSING  # re-export for predicate authors

__all__ = ["Predicate", "MISSING"]


@runtime_checkable
class Predicate(Protocol):
    key: str
    group: str
    label: str
    reads: list[str]
    params_schema: dict
    def matches(self, view: dict, params: dict) -> "bool | None": ...
    # optional: def sql_pushdown(self, params: dict): -> SQLAlchemy clause or None
