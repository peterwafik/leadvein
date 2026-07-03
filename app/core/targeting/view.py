from __future__ import annotations

import json

_MISSING = object()
MISSING = _MISSING  # sentinel: path absent (distinct from a stored None/False)


def _load(blob: str) -> dict:
    try:
        return json.loads(blob or "{}") or {}
    except (ValueError, TypeError):
        return {}


def _load_list(blob: str):
    return json.loads(blob or "[]")


# key -> (source blob attribute, loader). Parsing these JSON blobs dominates the
# estimate hot path (~9k candidates/call), yet most predicates read none of them.
# The view defers each parse until the key is actually read (see _LazyView),
# so a candidate that only touches scalar columns (country/score) pays zero JSON
# cost. Decisions are identical: the same value is produced, just on first access.
_LAZY_FIELDS = {
    "category_keys": ("category_keys_json", _load_list),
    "validation": ("validation_json", _load),
    "subscores": ("subscores_json", _load),
    "attributes": ("attributes_json", _load),
    "intent": ("intent_json", _load),
}


class _LazyView(dict):
    """dict subclass whose JSON-derived keys parse lazily on first access and
    then cache. Behaves exactly like the eager dict for reads via ``[]``, ``in``,
    ``get`` and ``get_path`` (the only access patterns used on a view)."""

    __slots__ = ("_lead",)

    def __init__(self, scalars: dict, lead):
        super().__init__(scalars)
        self._lead = lead

    def __missing__(self, key):
        spec = _LAZY_FIELDS.get(key)
        if spec is None:
            raise KeyError(key)
        attr, loader = spec
        val = loader(getattr(self._lead, attr))
        dict.__setitem__(self, key, val)
        return val

    def __contains__(self, key):
        return dict.__contains__(self, key) or key in _LAZY_FIELDS

    def get(self, key, default=None):
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        if key in _LAZY_FIELDS:
            return self[key]
        return default

    def keys(self):
        return list(super().keys()) + [k for k in _LAZY_FIELDS
                                       if not dict.__contains__(self, k)]


def lead_view(lead) -> dict:
    scalars = {
        "id": lead.id, "business_name": lead.business_name,
        "city": lead.city, "region": lead.region, "country": lead.country,
        "postal_code": lead.postal_code, "latitude": lead.latitude, "longitude": lead.longitude,
        "phone": lead.phone, "public_email": lead.public_email, "website_url": lead.website_url,
        "opening_hours": getattr(lead, "opening_hours", ""),
        "completeness_score": lead.completeness_score,
        "score_total": lead.score_total,
        "source_key": lead.source_key, "source_license": lead.source_license,
        "scoring_profile_key": lead.scoring_profile_key,
        "date_discovered": lead.date_discovered, "date_last_verified": lead.date_last_verified,
        "retention_expiry": lead.retention_expiry, "times_sold": lead.times_sold,
    }
    return _LazyView(scalars, lead)


def get_path(view: dict, path: str):
    cur = view
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return MISSING
    return cur
