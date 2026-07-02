"""Tests for web.runs_tech predicate (Task 4).

Step 1 (failing): ensure the predicate matches correctly on a lead view with
attributes.recipe_key + attributes.match_strength, tri-states correctly on absent
data, and returns None for empty recipe_in.
"""
import json
import pytest
from app.core.db import Lead
from app.core.targeting.view import lead_view
from app.targeting.predicates.webpresence import RUNS_TECH


def _view(recipe_key=None, match_strength=None):
    attrs = {}
    if recipe_key is not None:
        attrs["recipe_key"] = recipe_key
    if match_strength is not None:
        attrs["match_strength"] = match_strength
    return lead_view(Lead(
        city="London", country="GB", phone="", public_email="",
        score_total=50,
        attributes_json=json.dumps(attrs),
        intent_json="{}", subscores_json="{}", category_keys_json="[]",
    ))


def test_matches_true_for_exact_recipe_and_min_strength():
    """Lead runs gloriafood with strength 2; min_strength=2 → True."""
    v = _view(recipe_key="gloriafood", match_strength=2)
    assert RUNS_TECH.matches(v, {"recipe_in": ["gloriafood"], "min_strength": 2}) is True


def test_matches_false_for_insufficient_strength():
    """Lead strength=2 < min_strength=3 → False."""
    v = _view(recipe_key="gloriafood", match_strength=2)
    assert RUNS_TECH.matches(v, {"recipe_in": ["gloriafood"], "min_strength": 3}) is False


def test_matches_false_for_different_recipe():
    """Lead runs gloriafood but recipe_in only has shopify → False."""
    v = _view(recipe_key="gloriafood", match_strength=2)
    assert RUNS_TECH.matches(v, {"recipe_in": ["shopify"], "min_strength": 1}) is False


def test_matches_none_when_no_recipe_key():
    """Lead has no recipe_key in attributes → tri-state None (un-fingerprinted)."""
    v = _view()
    assert RUNS_TECH.matches(v, {"recipe_in": ["gloriafood"], "min_strength": 1}) is None


def test_matches_none_for_empty_recipe_in():
    """Empty recipe_in list → None (no filter intent expressed)."""
    v = _view(recipe_key="gloriafood", match_strength=2)
    assert RUNS_TECH.matches(v, {"recipe_in": [], "min_strength": 1}) is None
