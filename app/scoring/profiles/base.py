from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ScoringProfile(Protocol):
    key: str

    def combine(self, lead: dict, base: dict) -> dict: ...
