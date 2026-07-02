"""Fingerprint recipe library — CRUD helpers + catalog seed.

Public API:
    list_recipes(session, *, enabled=None, category=None) -> list[FingerprintRecipe]
    get_recipe(session, recipe_key) -> FingerprintRecipe | None
    seed_recipes(session) -> int
"""
from __future__ import annotations

from sqlmodel import Session, select

from app.fingerprints.models import FingerprintRecipe
from app.fingerprints.catalog import CUSTOM_RECIPES


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def list_recipes(
    session: Session,
    *,
    enabled: bool | None = None,
    category: str | None = None,
) -> list[FingerprintRecipe]:
    """Return recipes, optionally filtered by *enabled* and/or *category*."""
    q = select(FingerprintRecipe)
    if enabled is not None:
        q = q.where(FingerprintRecipe.enabled == enabled)
    if category is not None:
        q = q.where(FingerprintRecipe.category == category)
    return list(session.exec(q).all())


def get_recipe(session: Session, recipe_key: str) -> FingerprintRecipe | None:
    """Look up a single recipe by its unique key."""
    return session.exec(
        select(FingerprintRecipe).where(FingerprintRecipe.recipe_key == recipe_key)
    ).first()


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def seed_recipes(session: Session) -> int:
    """Idempotent upsert of CUSTOM_RECIPES from the catalog.

    Rows that already exist (matched by recipe_key) are NEVER overwritten, so
    operator edits made through the admin UI are preserved across restarts.

    Returns the total number of recipes in the catalog (not just rows inserted
    on this call).
    """
    for defn in CUSTOM_RECIPES:
        if get_recipe(session, defn["recipe_key"]) is None:
            recipe = FingerprintRecipe(**defn)
            session.add(recipe)
            session.commit()
    return len(CUSTOM_RECIPES)
