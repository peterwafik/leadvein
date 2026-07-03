"""Pushdown upgrades: OR-groups + extra clauses narrow in SQL; results are
provably identical to pure-Python evaluation (superset honesty)."""
from __future__ import annotations

import json

from sqlmodel import Session, select

import app.leadvault as lv
from app.core.db import Lead
from app.core.targeting.composition import (_pushdown_clauses,
                                            matching_by_composition, selects)
from app.core.targeting.view import lead_view


def _mk(city, country, score):
    return Lead(business_name=f"P-{city}-{score}", city=city, country=country,
                score_total=score, category_keys_json="[]",
                validation_json=json.dumps({"profile": {"tier": "validated"},
                                            "phone": {"tier": "validated"}}))


def _seed(s):
    for city, cc, sc in [("Pushtown", "GB", 90), ("Pushville", "GB", 40),
                          ("Pushberg", "DE", 90)]:
        s.add(_mk(city, cc, sc))
    s.commit()


OR_GEO = {"op": "AND", "nodes": [
    {"op": "OR", "nodes": [
        {"predicate": "geo.country_any", "params": {"in": ["DE"]}},
        {"predicate": "geo.city_any", "params": {"in": ["Pushtown"]}}]},
    {"predicate": "quality.min_score", "params": {"min": 50}}]}


def test_or_group_pushdown_emits_clause():
    with Session(lv.engine) as s:
        clauses = _pushdown_clauses(s, OR_GEO)
    assert clauses and len(clauses) == 2      # or_(...) + min_score


def test_pushdown_equals_pure_python():
    with Session(lv.engine) as s:
        _seed(s)
        pushed = {l.id for l in matching_by_composition(s, OR_GEO)}
        pure = {l.id for l in s.exec(select(Lead)).all()
                if selects(lead_view(l), OR_GEO)}
        assert pushed == pure


def test_or_group_with_unpushable_child_falls_back():
    comp = {"op": "AND", "nodes": [
        {"op": "OR", "nodes": [
            {"predicate": "geo.city_any", "params": {"in": ["Pushtown"]}},
            {"predicate": "web.has_signal", "params": {"signal": "x"}}]}]}
    with Session(lv.engine) as s:
        _seed(s)
        clauses = _pushdown_clauses(s, comp)
        # OR group skipped (has_signal has no pushdown) -> no clause for it
        assert not clauses
        pushed = {l.id for l in matching_by_composition(s, comp)}
        pure = {l.id for l in s.exec(select(Lead)).all()
                if selects(lead_view(l), comp)}
        assert pushed == pure


def test_extra_clauses_narrow():
    with Session(lv.engine) as s:
        _seed(s)
        rows = matching_by_composition(
            s, {"op": "AND", "nodes": []},
            extra_clauses=[Lead.score_total >= 90])
        assert rows and all(l.score_total >= 90 for l in rows)


def test_or_group_with_negated_child_falls_back():
    comp = {"op": "AND", "nodes": [
        {"op": "OR", "nodes": [
            {"predicate": "geo.city_any", "params": {"in": ["Pushtown"]}},
            {"predicate": "geo.country_any", "params": {"in": ["DE"]}, "negate": True}]}]}
    with Session(lv.engine) as s:
        _seed(s)
        clauses = _pushdown_clauses(s, comp)
        assert not clauses
        pushed = {l.id for l in matching_by_composition(s, comp)}
        pure = {l.id for l in s.exec(select(Lead)).all()
                if selects(lead_view(l), comp)}
        assert pushed == pure
