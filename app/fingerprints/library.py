"""Fingerprint recipe library — CRUD helpers + catalog seed.

Public API:
    list_recipes(session, *, enabled=None, category=None) -> list[FingerprintRecipe]
    get_recipe(session, recipe_key) -> FingerprintRecipe | None
    seed_recipes(session) -> int
    to_engine_recipe(row) -> Recipe
    test_recipe(session, recipe_key, *, discover_fn, fetch_fn, n=5) -> dict
    promote_recipe(session, recipe_key) -> FingerprintRecipe | None
    demote_recipe(session, recipe_key) -> FingerprintRecipe | None
"""
from __future__ import annotations

import json
from typing import Callable

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

def to_engine_recipe(row: FingerprintRecipe):
    """Convert a FingerprintRecipe DB row to an engine Recipe (for use with analyse/discover)."""
    from app.engine.recipes import Recipe
    return Recipe(
        id=row.recipe_key,
        category=row.category,
        type=row.tech_type,
        urlscan_query=row.urlscan_query,
        publicwww_query=row.publicwww_query,
        verify_fingerprints=json.loads(row.verify_fingerprints_json),
        id_extractors=json.loads(row.id_extractors_json),
        exclude_hosts=json.loads(row.exclude_hosts_json),
        is_builtin=False,
    )


# ---------------------------------------------------------------------------
# Precision test
# ---------------------------------------------------------------------------

def test_recipe(
    session: Session,
    recipe_key: str,
    *,
    discover_fn: Callable,
    fetch_fn: Callable,
    n: int = 5,
) -> dict:
    """Precision-test a recipe by discovering ~n candidates and verifying each
    on its OWN homepage.

    Args:
        session:      DB session (used to load the recipe row).
        recipe_key:   Key of the recipe to test.
        discover_fn:  ``(recipe) -> list[str]`` — returns candidate host strings.
                      Injected in tests; use engine_discover in production.
        fetch_fn:     ``(url, **kw) -> (final_url, html)`` — fetches a homepage.
                      Injected in tests; use engine_fetch in production.
        n:            Maximum number of candidates to test (default 5).

    Returns a dict::

        {
            "recipe_key": str,
            "tested":     int,         # candidates where HTML was returned
            "matched":    int,         # of those, ≥1 verify_fingerprint present
            "precision":  float,       # matched/tested  (0.0 when tested==0)
            "samples": [
                {
                    "host":           str,
                    "business_name":  str,
                    "matched":        list[str],   # fingerprints found on page
                    "phone_present":  bool,
                    "email_present":  bool,
                },
                ...
            ],
        }

    When the recipe is not found, ``tested==0``, ``precision==0.0``, and the
    dict contains an ``"error"`` key.
    """
    from app.engine.enrich import norm_url, analyse

    row = get_recipe(session, recipe_key)
    if row is None:
        return {
            "recipe_key": recipe_key,
            "tested": 0,
            "matched": 0,
            "precision": 0.0,
            "samples": [],
            "error": f"recipe not found: {recipe_key!r}",
        }

    recipe = to_engine_recipe(row)
    candidates: list[str] = list(discover_fn(recipe))[:n]

    tested   = 0
    matched  = 0
    samples: list[dict] = []

    for host in candidates:
        url = norm_url(host)
        final_url, html = fetch_fn(url)

        if html is None:
            continue  # fetch failed — skip; not counted as tested

        tested += 1

        # Own-homepage confirmation: count how many verify_fingerprints appear.
        low_html = html.lower()
        matched_fps = [
            fp for fp in recipe.verify_fingerprints
            if fp.lower() in low_html
        ]

        if matched_fps:
            matched += 1

        # Enrich for business-entity fields only — NEVER include raw personal data.
        lead = analyse(recipe, final_url or url, html)

        samples.append({
            "host":          host,
            "business_name": lead.name,
            "matched":       matched_fps,
            "phone_present": bool(lead.phones),
            "email_present": bool(lead.emails),
        })

    precision = matched / tested if tested > 0 else 0.0

    return {
        "recipe_key": recipe_key,
        "tested":     tested,
        "matched":    matched,
        "precision":  precision,
        "samples":    samples,
    }


# ---------------------------------------------------------------------------
# Promote / demote
# ---------------------------------------------------------------------------

def promote_recipe(session: Session, recipe_key: str) -> FingerprintRecipe | None:
    """Set ``enabled=True`` on a recipe.

    Intended to be called only after a passing precision test.  Returns the
    updated row, or ``None`` if the recipe key is not found.
    """
    row = get_recipe(session, recipe_key)
    if row is None:
        return None
    row.enabled = True
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def demote_recipe(session: Session, recipe_key: str) -> FingerprintRecipe | None:
    """Set ``enabled=False`` (grey) on a recipe.  Returns the updated row or
    ``None`` if not found."""
    row = get_recipe(session, recipe_key)
    if row is None:
        return None
    row.enabled = False
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


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
