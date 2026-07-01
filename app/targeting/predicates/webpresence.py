from __future__ import annotations
from app.core.targeting.view import get_path, MISSING


class _HasSignal:   # tri-state exerciser
    key = "web.has_signal"; group = "web_presence"; label = "Web signal present"
    reads = ["intent"]; params_schema = {"signal": "string"}
    def matches(self, view, params):
        val = get_path(view, f"intent.{params.get('signal', '')}")
        return None if val is MISSING else bool(val)


class _IsEnriched:   # meta: never unknown
    key = "web.is_enriched"; group = "web_presence"; label = "Web-enriched"
    reads = ["intent.last_scanned"]; params_schema = {}
    def matches(self, view, params):
        return get_path(view, "intent.last_scanned") is not MISSING


HAS_SIGNAL = _HasSignal(); IS_ENRICHED = _IsEnriched()
