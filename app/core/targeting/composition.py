from __future__ import annotations

from app.core.targeting import registry


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
