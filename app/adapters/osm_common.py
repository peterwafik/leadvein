"""Shared OSM tags -> NormalizedLead mapping.

Single source of truth used by BOTH the Overpass adapter (ad-hoc city pulls)
and the bulk PBF importer, so the field mapping cannot drift between them."""
from __future__ import annotations

from app.adapters.base import NormalizedLead


def normalized_from_tags(tags: dict, *, lat, lon, raw_ref: str,
                         categories: list[str], source_key: str) -> NormalizedLead | None:
    name = (tags or {}).get("name") or ""
    if not name:
        return None          # business-entity rule: nameless POIs are not leads
    house = tags.get("addr:housenumber", "")
    street = tags.get("addr:street", "")
    line1 = " ".join(x for x in (house, street) if x)
    opening = tags.get("opening_hours", "") or ""
    # open_7_days: exact derivation copied from app/adapters/osm.py:86-87
    open_7_days = "Su" in opening or "Mo-Su" in opening
    return NormalizedLead(
        business_name=name,
        category_keys=list(categories or []),
        address={"line1": line1, "city": tags.get("addr:city", ""),
                 "region": tags.get("addr:state", ""),
                 "postal_code": tags.get("addr:postcode", ""),
                 "country": tags.get("addr:country", ""),
                 "lat": lat, "lon": lon},
        phone=tags.get("phone") or tags.get("contact:phone", "") or "",
        public_email=tags.get("email") or tags.get("contact:email", "") or "",
        website_url=tags.get("website") or tags.get("contact:website", "") or "",
        opening_hours=opening,
        attributes={"open_7_days": open_7_days},
        source_key=source_key,
        raw_ref=raw_ref,
    )
