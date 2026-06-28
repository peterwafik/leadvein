from __future__ import annotations

import json

from sqlmodel import Session, select

from app.core.db import LeadSource


def ensure_source(session: Session, meta) -> None:
    """Create a LeadSource row for *meta* if one does not already exist.

    *meta* must expose: .key, .name, .type, .url, .license,
    .terms_status, and .regions.
    """
    if not session.exec(select(LeadSource).where(LeadSource.key == meta.key)).first():
        session.add(LeadSource(
            key=meta.key,
            name=meta.name,
            type=meta.type,
            url=meta.url,
            license=meta.license,
            terms_status=meta.terms_status,
            regions_json=json.dumps(meta.regions),
        ))
        session.commit()
