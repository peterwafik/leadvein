"""Test suite for fingerprint recipe catalog library.

Step 1 (TDD): write tests first so they fail before implementation.
Steps 2-4: implement, then verify pass.
"""
from __future__ import annotations

import json

from sqlmodel import Session

import app.fingerprints.models  # noqa — register table before init_db
from app.core.db import init_db
from app.fingerprints.library import list_recipes, get_recipe, seed_recipes


def _fresh_session():
    """Return a Session backed by an isolated in-memory SQLite DB."""
    e = init_db("sqlite://")
    return Session(e)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_seed_idempotent():
    """seed_recipes returns catalog count on every call; rows are not duplicated."""
    with _fresh_session() as s:
        count = seed_recipes(s)
        assert count > 0
        seed_recipes(s)           # second call must be a no-op
        assert len(list_recipes(s)) == count


# ---------------------------------------------------------------------------
# list_recipes enabled filter — high-confidence set present
# ---------------------------------------------------------------------------

def test_list_recipes_enabled_includes_high_confidence():
    """list_recipes(enabled=True) includes gloriafood, chownow, shopify."""
    with _fresh_session() as s:
        seed_recipes(s)
        enabled = list_recipes(s, enabled=True)
        keys = {r.recipe_key for r in enabled}
        assert "gloriafood" in keys, f"gloriafood missing from enabled set; got {keys}"
        assert "chownow" in keys, f"chownow missing from enabled set; got {keys}"
        assert "shopify" in keys, f"shopify missing from enabled set; got {keys}"


# ---------------------------------------------------------------------------
# list_recipes enabled filter — greyed set absent
# ---------------------------------------------------------------------------

def test_list_recipes_enabled_excludes_greyed():
    """list_recipes(enabled=True) must NOT include greyed/low-confidence recipes."""
    with _fresh_session() as s:
        seed_recipes(s)
        enabled = list_recipes(s, enabled=True)
        keys = {r.recipe_key for r in enabled}
        assert "stripe" not in keys, "stripe (greyed) must not appear in enabled set"
        assert "wordpress" not in keys, "wordpress (greyed) must not appear in enabled set"
        assert "google_analytics" not in keys, "google_analytics (greyed) must not appear in enabled set"


# ---------------------------------------------------------------------------
# Greyed recipe field invariants
# ---------------------------------------------------------------------------

def test_greyed_recipe_confidence_and_enabled_false():
    """Greyed recipes have confidence='low' and enabled=False."""
    with _fresh_session() as s:
        seed_recipes(s)
        for key in ("stripe", "wordpress", "google_analytics"):
            r = get_recipe(s, key)
            assert r is not None, f"{key!r} not found in DB"
            assert r.confidence == "low", f"{key}: expected confidence='low', got {r.confidence!r}"
            assert r.enabled is False, f"{key}: expected enabled=False, got {r.enabled!r}"


# ---------------------------------------------------------------------------
# gloriafood verbatim extractors
# ---------------------------------------------------------------------------

def test_gloriafood_extractors_verbatim():
    """get_recipe('gloriafood') carries the ruid/cuid extractors verbatim from BUILTIN_RECIPES."""
    with _fresh_session() as s:
        seed_recipes(s)
        r = get_recipe(s, "gloriafood")
        assert r is not None, "gloriafood recipe not found in DB"
        extractors = json.loads(r.id_extractors_json)
        # Verbatim from app/engine/recipes.py BUILTIN_RECIPES
        assert "ruid" in extractors, "ruid extractor missing"
        assert "cuid" in extractors, "cuid extractor missing"
        assert extractors["ruid"] == r'data-glf-ruid=["\']([0-9a-fA-F-]+)["\']'
        assert extractors["cuid"] == r'data-glf-cuid=["\']([0-9a-fA-F-]+)["\']'
