from __future__ import annotations

from sqlmodel import select

from app.core.db import Lead
from app.core.leadcats import lead_ids_for_categories
from app.core.targeting import registry
from app.core.targeting.view import lead_view


def kleene_not(v):
    return None if v is None else (not v)


def kleene_and(vals):
    if any(v is False for v in vals):
        return False
    if any(v is None for v in vals):
        return None
    return True


def kleene_or(vals):
    if any(v is True for v in vals):
        return True
    if any(v is None for v in vals):
        return None
    return False


def evaluate(view: dict, node: dict):
    if "op" in node:
        vals = [evaluate(view, child) for child in node.get("nodes", [])]
        op = node["op"]
        if op == "AND":
            return kleene_and(vals)
        if op == "OR":
            return kleene_or(vals)
        raise ValueError(f"unknown composition op: {op!r}")
    pred = registry.get(node["predicate"])
    v = pred.matches(view, node.get("params", {}))
    if node.get("negate"):
        v = kleene_not(v)
    return v


def selects(view: dict, composition: dict) -> bool:
    return evaluate(view, composition) is True


def _pushdown_clauses(session, composition):
    """Sound, conservative pushdown: only for a top-level AND, only non-negated leaves whose
    predicate exposes sql_pushdown (or category.any via the link table). Returns a list of
    SQLAlchemy clauses, or None to signal 'no safe pushdown -> scan all'."""
    if composition.get("op") != "AND":
        return None
    clauses = []
    for node in composition.get("nodes", []):
        if "op" in node or node.get("negate"):
            continue  # nested groups / negation are not pushed (handled in Python)
        pred = registry.get(node["predicate"])
        params = node.get("params", {})
        if pred.key == "category.any":
            ids = lead_ids_for_categories(session, params.get("in") or [])
            clauses.append(Lead.id.in_(ids) if ids else Lead.id.in_([-1]))
            continue
        fn = getattr(pred, "sql_pushdown", None)
        if fn is not None:
            clause = fn(params)
            if clause is not None:
                clauses.append(clause)
    return clauses


def matching_by_composition(session, composition, *, exclude_lead_ids=frozenset()):
    clauses = _pushdown_clauses(session, composition)
    if clauses:
        candidates = session.exec(select(Lead).where(*clauses)).all()
    else:
        candidates = session.exec(select(Lead)).all()
    out = []
    for lead in candidates:
        if lead.id in exclude_lead_ids:
            continue
        if selects(lead_view(lead), composition):
            out.append(lead)
    return out
