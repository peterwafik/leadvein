from __future__ import annotations
from app.core.targeting import registry
from app.core.targeting.coverage import populated_paths, coverage_pct


def _desc(session, p) -> dict:
    return {"key": p.key, "group": p.group, "label": p.label,
            "params_schema": p.params_schema,
            "coverage_pct": {r: coverage_pct(session, r) for r in p.reads}}


def predicate_options(session) -> dict:
    pop = populated_paths(session)
    available, unavailable = [], []
    for k in registry.all_keys():
        p = registry.get(k)
        (available if set(p.reads) <= pop else unavailable).append(_desc(session, p))
    return {"available": available, "unavailable": unavailable}
