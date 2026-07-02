"""Live inventory coverage per geography — the honesty layer of the geo control.

Counts include ONLY leads a buyer could actually be served (not expired, not
opted out, passing serve filters incl. the quality gate). A 60s TTL cache keeps
this cheap; ingestion-sized changes surface within a minute or on invalidate().
"""
from __future__ import annotations

import time

from sqlmodel import Session, select

from app.core.compliance import lead_opted_out
from app.core.db import Lead
from app.core.retention import is_expired
from app.core.serve_filters import passes_serve_filters

_TTL = 60.0
_cache: dict = {"at": 0.0, "data": None}


def invalidate_geo_counts() -> None:
    _cache["at"] = 0.0
    _cache["data"] = None


def geo_lead_counts(session: Session) -> dict:
    now = time.monotonic()
    if _cache["data"] is not None and now - _cache["at"] < _TTL:
        return _cache["data"]
    countries: dict[str, int] = {}
    cities: dict[tuple[str, str], int] = {}
    regions: dict[tuple[str, str], int] = {}
    city_names: dict[str, str] = {}
    for lead in session.exec(select(Lead)).all():
        if is_expired(lead) or lead_opted_out(session, lead):
            continue
        if not passes_serve_filters(session, None, lead, None):
            continue
        cc = (lead.country or "").upper()
        if cc:
            countries[cc] = countries.get(cc, 0) + 1
        if lead.city:
            key = (cc, lead.city.strip().lower())
            cities[key] = cities.get(key, 0) + 1
            city_names.setdefault(lead.city.strip().lower(), lead.city.strip())
        if lead.region:
            rkey = (cc, lead.region.strip().lower())
            regions[rkey] = regions.get(rkey, 0) + 1
    data = {"countries": countries, "cities": cities, "regions": regions,
            "city_names": city_names}
    _cache["at"] = now
    _cache["data"] = data
    return data
