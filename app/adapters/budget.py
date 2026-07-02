"""Per-source credit/rate budget and per-field provenance helpers.

All identifiers are generic (source_key is a data value, never a hard-coded
provider name string in core logic).
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlmodel import Session, select

from app.core.db import SourceBudget, _now

if TYPE_CHECKING:
    from app.core.db import Lead


# ---------------------------------------------------------------------------
# Budget helpers
# ---------------------------------------------------------------------------

def _get_or_create(session: Session, source_key: str, cap: int) -> SourceBudget:
    """Return the SourceBudget row for *source_key*, creating it if absent."""
    row = session.exec(
        select(SourceBudget).where(SourceBudget.source_key == source_key)
    ).first()
    if row is None:
        row = SourceBudget(source_key=source_key, used=0, cap=cap)
        session.add(row)
        session.flush()
    return row


def record_use(session: Session, source_key: str, cap: int, n: int = 1) -> int:
    """Increment *used* by *n* for *source_key* (upsert). Returns new used total.

    The *cap* is written/updated on every call so the latest cap wins.
    """
    row = _get_or_create(session, source_key, cap)
    row.used += n
    row.cap = cap
    row.updated_at = _now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row.used


def remaining(session: Session, source_key: str, cap: int) -> int:
    """Return max(0, cap - used) — never goes negative."""
    row = session.exec(
        select(SourceBudget).where(SourceBudget.source_key == source_key)
    ).first()
    used = row.used if row is not None else 0
    return max(0, cap - used)


def would_exceed(session: Session, source_key: str, cap: int, n: int = 1) -> bool:
    """Return True if adding *n* more uses would push used above *cap*."""
    row = session.exec(
        select(SourceBudget).where(SourceBudget.source_key == source_key)
    ).first()
    used = row.used if row is not None else 0
    return (used + n) > cap


# ---------------------------------------------------------------------------
# Provenance helper
# ---------------------------------------------------------------------------

def stamp_provenance(lead: "Lead", field: str, source: str, license: str) -> None:  # noqa: A002
    """Write per-field provenance into *lead.field_provenance_json*.

    Structure: ``{field: {"source": str, "license": str, "at": str}}``.
    Existing entries for *other* fields are preserved; the entry for *field*
    is always overwritten with fresh data.
    """
    data: dict = json.loads(lead.field_provenance_json or "{}")
    data[field] = {"source": source, "license": license, "at": _now()}
    lead.field_provenance_json = json.dumps(data)
