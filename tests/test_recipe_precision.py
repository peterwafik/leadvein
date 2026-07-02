"""Tests for fingerprint recipe precision tool (Task 6).

Step 1 (TDD): write tests first so they fail before implementation.
Steps 2–4: implement, then verify pass.

Scenario: 5 mocked candidates, 3 have the fingerprint on their homepage,
2 don't → precision==0.6, matched==3, tested==5.
Samples carry BUSINESS-ENTITY fields only — no personal data.
"""
from __future__ import annotations

import app.fingerprints.models  # noqa — register table before init_db
from sqlmodel import Session

from app.core.db import init_db
from app.fingerprints.library import (
    seed_recipes,
    test_recipe as run_test_recipe,   # alias avoids pytest collecting this as a test
    promote_recipe,
    get_recipe,
)

# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

# GloriaFood-powered homepage — contains fbgcdn.com CDN asset, ewm2.js, and
# data-glf-ruid / data-glf-cuid attributes.  Expected: ≥1 fingerprint matched.
MATCHING_HTML = (
    "<html><head>"
    "<title>Mario's Pizza</title>"
    "<meta property=\"og:site_name\" content=\"Mario's Pizza\">"
    "</head><body>"
    "<script src=\"https://fbgcdn.com/embedder/js/ewm2.js\"></script>"
    "<div data-glf-cuid=\"cafe0000-cafe-cafe-cafe-000000000001\""
    "     data-glf-ruid=\"abcd1234-ab12-ab12-ab12-abcd12345678\"></div>"
    "<a href=\"mailto:info@marios.com\">Email us</a>"
    "<a href=\"tel:+441234567890\">Call us</a>"
    "</body></html>"
)

# Homepage with NO GloriaFood fingerprint tokens — surfaced by urlscan but
# zero verify_fingerprints are present.  Expected: matched==False.
NO_MATCH_HTML = (
    "<html><head><title>Burger Joint</title></head>"
    "<body><p>Order online at our website.</p>"
    "<a href=\"mailto:hello@burgerjoint.com\">Contact</a>"
    "</body></html>"
)


# ---------------------------------------------------------------------------
# Helper: in-memory DB seeded with catalog
# ---------------------------------------------------------------------------

def _fresh_session() -> Session:
    engine = init_db("sqlite://")
    session = Session(engine)
    seed_recipes(session)
    return session


# ---------------------------------------------------------------------------
# Mocked discover_fn and fetch_fn
# ---------------------------------------------------------------------------

FIVE_HOSTS = [
    "marios.com",       # match
    "joes-pizza.com",   # match
    "cafe-belle.com",   # match
    "burger-joint.com", # no match
    "plain-diner.com",  # no match
]
MATCHING_SET = frozenset({"marios.com", "joes-pizza.com", "cafe-belle.com"})


def _fake_discover(recipe):
    """Return exactly 5 host strings regardless of recipe."""
    return list(FIVE_HOSTS)


def _fake_fetch(url, **_):
    """Return MATCHING_HTML for the first 3 hosts, NO_MATCH_HTML for the last 2."""
    host = url.replace("https://", "").replace("http://", "").rstrip("/")
    if host in MATCHING_SET:
        return url, MATCHING_HTML
    return url, NO_MATCH_HTML


# ---------------------------------------------------------------------------
# Core precision tests (Step 1 — FAIL before test_recipe is implemented)
# ---------------------------------------------------------------------------

def test_precision_3_of_5():
    """5 candidates, 3 with fingerprint → tested==5, matched==3, precision==0.6."""
    with _fresh_session() as session:
        result = run_test_recipe(
            session, "gloriafood",
            discover_fn=_fake_discover,
            fetch_fn=_fake_fetch,
            n=5,
        )

    assert result["recipe_key"] == "gloriafood"
    assert result["tested"] == 5
    assert result["matched"] == 3
    assert abs(result["precision"] - 0.6) < 1e-9


def test_samples_length():
    """Result contains exactly 5 samples — one per tested candidate."""
    with _fresh_session() as session:
        result = run_test_recipe(
            session, "gloriafood",
            discover_fn=_fake_discover,
            fetch_fn=_fake_fetch,
            n=5,
        )

    assert len(result["samples"]) == 5


def test_samples_business_entity_fields_only():
    """Samples carry BUSINESS-ENTITY fields only — no obviously-personal data."""
    with _fresh_session() as session:
        result = run_test_recipe(
            session, "gloriafood",
            discover_fn=_fake_discover,
            fetch_fn=_fake_fetch,
            n=5,
        )

    for sample in result["samples"]:
        # Required business-entity fields must be present
        assert "host" in sample
        assert "business_name" in sample
        assert "matched" in sample
        assert "phone_present" in sample
        assert "email_present" in sample

        # No obviously-personal fields
        personal_fields = {
            "first_name", "last_name", "full_name", "person_name",
            "personal_email", "dob", "date_of_birth", "ssn",
            "passport", "national_id", "gender",
        }
        for pf in personal_fields:
            assert pf not in sample, (
                f"personal field {pf!r} must not appear in sample; got keys={set(sample)}"
            )

        # Type safety
        assert isinstance(sample["matched"], list)
        assert isinstance(sample["phone_present"], bool)
        assert isinstance(sample["email_present"], bool)


def test_matched_samples_have_fingerprints():
    """Matched samples contain ≥1 fingerprint string; unmatched have empty list."""
    with _fresh_session() as session:
        result = run_test_recipe(
            session, "gloriafood",
            discover_fn=_fake_discover,
            fetch_fn=_fake_fetch,
            n=5,
        )

    matched_samples   = [s for s in result["samples"] if s["matched"]]
    unmatched_samples = [s for s in result["samples"] if not s["matched"]]

    assert len(matched_samples)   == 3, f"expected 3 matched samples; got {len(matched_samples)}"
    assert len(unmatched_samples) == 2, f"expected 2 unmatched samples; got {len(unmatched_samples)}"

    for s in matched_samples:
        assert len(s["matched"]) >= 1
        # fbgcdn.com is in gloriafood verify_fingerprints and is present in MATCHING_HTML
        assert "fbgcdn.com" in s["matched"], (
            f"fbgcdn.com must be in matched list; got {s['matched']}"
        )


def test_precision_zero_no_candidates():
    """Empty discover → tested==0, matched==0, precision==0.0, samples==[]."""
    with _fresh_session() as session:
        result = run_test_recipe(
            session, "gloriafood",
            discover_fn=lambda recipe: [],
            fetch_fn=_fake_fetch,
            n=5,
        )

    assert result["tested"]    == 0
    assert result["matched"]   == 0
    assert result["precision"] == 0.0
    assert result["samples"]   == []


def test_unknown_recipe_returns_error():
    """Unknown recipe_key → tested==0, precision==0.0, 'error' key present."""
    with _fresh_session() as session:
        result = run_test_recipe(
            session, "does_not_exist",
            discover_fn=_fake_discover,
            fetch_fn=_fake_fetch,
        )

    assert result["tested"]    == 0
    assert result["matched"]   == 0
    assert result["precision"] == 0.0
    assert "error" in result


# ---------------------------------------------------------------------------
# promote_recipe
# ---------------------------------------------------------------------------

def test_promote_recipe_sets_enabled():
    """promote_recipe flips enabled=True on a greyed (enabled=False) recipe."""
    with _fresh_session() as session:
        before = get_recipe(session, "wordpress")
        assert before is not None and before.enabled is False, (
            "wordpress must be greyed in catalog"
        )
        promote_recipe(session, "wordpress")
        after = get_recipe(session, "wordpress")
        assert after is not None and after.enabled is True


def test_promote_recipe_nonexistent_returns_none():
    """promote_recipe on an unknown key returns None without raising."""
    with _fresh_session() as session:
        result = promote_recipe(session, "nonexistent_key")
    assert result is None
