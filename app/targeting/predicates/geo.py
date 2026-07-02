from __future__ import annotations
from sqlalchemy import or_
from app.core.db import Lead
from app.core.targeting.view import get_path, MISSING


class _GeoEq:
    def __init__(self, key, path, column, label):
        self.key = key; self.group = "geographic"; self.label = label
        self.reads = [path]; self.params_schema = {"value": "string"}
        self._path = path; self._col = column
    def matches(self, view, params):
        val = get_path(view, self._path)
        if val is MISSING or val in (None, ""):
            return None
        want = (params.get("value") or "")
        return want.lower() in str(val).lower() if want else None
    def sql_pushdown(self, session, params):
        want = (params.get("value") or "")
        return self._col.ilike(f"%{want}%") if want else None


class _GeoAny:
    def __init__(self, key, path, column, label):
        self.key = key; self.group = "geographic"; self.label = label
        self.reads = [path]; self.params_schema = {"in": "list[string]"}
        self._path = path; self._col = column
    def matches(self, view, params):
        val = get_path(view, self._path)
        if val is MISSING or val in (None, ""):
            return None
        want = [v for v in (params.get("in") or []) if v]
        if not want:
            return None
        val_lower = str(val).lower()
        return any(v.lower() in val_lower for v in want)
    def sql_pushdown(self, session, params):
        want = [v for v in (params.get("in") or []) if v]
        if not want:
            return None
        return or_(*[self._col.ilike(f"%{v}%") for v in want])


GEO_COUNTRY = _GeoEq("geo.country", "country", Lead.country, "Country")
GEO_REGION = _GeoEq("geo.region", "region", Lead.region, "Region")
GEO_CITY = _GeoEq("geo.city", "city", Lead.city, "City")

GEO_CITY_ANY = _GeoAny("geo.city_any", "city", Lead.city, "City is any of")
GEO_REGION_ANY = _GeoAny("geo.region_any", "region", Lead.region, "Region/State is any of")
GEO_COUNTRY_ANY = _GeoAny("geo.country_any", "country", Lead.country, "Country is any of")
