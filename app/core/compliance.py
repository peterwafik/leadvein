from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from sqlmodel import Session, select

from app.core.db import (OptOutRequest, SuppressionList, SuppressionEntry, AuditLog)


def host_of(url: str) -> str:
    if not url:
        return ""
    netloc = urlsplit(url if "//" in url else "https://" + url).netloc.lower()
    netloc = netloc.split(":")[0]
    return netloc[4:] if netloc.startswith("www.") else netloc


def _norm(kind: str, value: str) -> str:
    if kind == "domain":
        return host_of(value)
    if kind == "phone":
        return re.sub(r"\D", "", value)
    if kind in ("email", "business_name"):
        return value.strip().lower()
    return value.strip().lower()


def is_opted_out(session: Session, *, domain: str = "", phone: str = "",
                 email: str = "") -> bool:
    checks = [("domain", domain), ("phone", phone), ("email", email)]
    for kind, value in checks:
        if not value:
            continue
        rows = session.exec(select(OptOutRequest).where(
            OptOutRequest.kind == kind,
            OptOutRequest.applied == True)).all()  # noqa: E712
        norm_value = _norm(kind, value)
        for stored in rows:
            if _norm(kind, stored.value) == norm_value:
                return True
    return False


def is_suppressed(session: Session, buyer_account_id: int | None, *, domain: str = "",
                  phone: str = "", email: str = "", business_name: str = "") -> bool:
    lists = session.exec(select(SuppressionList).where(
        (SuppressionList.buyer_account_id == None)  # noqa: E711  (global)
        | (SuppressionList.buyer_account_id == buyer_account_id))).all()
    list_ids = [l.id for l in lists]
    if not list_ids:
        return False
    checks = [("domain", domain), ("phone", phone), ("email", email),
              ("business_name", business_name)]
    for kind, value in checks:
        if not value:
            continue
        entries = session.exec(select(SuppressionEntry).where(
            SuppressionEntry.list_id.in_(list_ids),
            SuppressionEntry.kind == kind)).all()
        norm_value = _norm(kind, value)
        for entry in entries:
            if _norm(kind, entry.value) == norm_value:
                return True
    return False


def audit(session: Session, actor_user_id, action: str, entity: str, entity_id: str,
          meta: dict | None = None) -> AuditLog:
    row = AuditLog(actor_user_id=actor_user_id, action=action, entity=entity,
                   entity_id=str(entity_id), meta_json=json.dumps(meta or {}))
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
