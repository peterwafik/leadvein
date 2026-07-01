from __future__ import annotations
from datetime import datetime, timezone
from app.core.db import Lead
from app.core.targeting.view import get_path, MISSING


class _MinScore:
    key = "quality.min_score"; group = "quality"; label = "Minimum score"
    reads = ["score_total"]; params_schema = {"min": "int"}
    def matches(self, view, params):
        return int(view.get("score_total", 0)) >= int(params.get("min", 0))
    def sql_pushdown(self, session, params):
        return Lead.score_total >= int(params.get("min", 0))


class _VerifiedWithin:
    key = "freshness.verified_within"; group = "freshness"; label = "Verified within N days"
    reads = ["date_last_verified"]; params_schema = {"days": "int"}
    def matches(self, view, params):
        iso = get_path(view, "date_last_verified")
        if iso is MISSING or not iso:
            return None
        try:
            dt = datetime.fromisoformat(iso)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
        return days <= int(params.get("days", 0))


class _SourceType:
    key = "source.type"; group = "verification"; label = "Source"
    reads = ["source_key"]; params_schema = {"value": "string"}
    def matches(self, view, params):
        val = get_path(view, "source_key")
        if val is MISSING or not val:
            return None
        return str(val) == params.get("value")
    def sql_pushdown(self, session, params):
        return Lead.source_key == params.get("value")


MIN_SCORE = _MinScore(); VERIFIED_WITHIN = _VerifiedWithin(); SOURCE_TYPE = _SourceType()
