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


class _RunsTech:
    """Tri-state predicate: True if lead's fingerprinted recipe is in recipe_in
    and match_strength >= min_strength; None when the lead has no recipe_key
    (un-fingerprinted); False when recipe doesn't match or strength is too low.
    Empty recipe_in → None (no filter intent expressed).
    """
    key = "web.runs_tech"; group = "technology"; label = "Runs technology"
    reads = ["attributes.recipe_key", "attributes.match_strength"]
    params_schema = {"recipe_in": "list[string]", "min_strength": "int"}

    def matches(self, view, params):
        recipe_in = params.get("recipe_in", [])
        if not recipe_in:
            return None
        rk = get_path(view, "attributes.recipe_key")
        if rk is MISSING:
            return None
        strength = get_path(view, "attributes.match_strength")
        if strength is MISSING:
            strength = 0
        return (rk in recipe_in
                and int(strength or 0) >= int(params.get("min_strength", 1)))


HAS_SIGNAL = _HasSignal(); IS_ENRICHED = _IsEnriched(); RUNS_TECH = _RunsTech()
