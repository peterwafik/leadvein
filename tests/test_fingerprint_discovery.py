"""Tests for FingerprintDiscoveryAdapter.

NO live network calls — discover_fn and fetch_fn are always injected.

Test scenarios:
(a) Canned GloriaFood homepage with fbgcdn.com + data-glf-ruid
    → NormalizedLead with match_strength >= 2, matched list, ruid captured.
(b) Homepage that only links to a vendor-like URL but has NO fingerprint
    tokens → normalize returns None  (INV-12: own-homepage confirmation).
(c) discover yields hosts for an enabled recipe; skips a disabled/greyed one.
"""
from __future__ import annotations

import pytest
from sqlmodel import Session

import app.fingerprints.models  # noqa — register table before init_db
from app.core.db import init_db
from app.fingerprints.library import seed_recipes
from app.adapters.base import AdapterQuery
from app.adapters.providers.fingerprint_discovery import FingerprintDiscoveryAdapter

# ---------------------------------------------------------------------------
# Canned HTML fixtures
# ---------------------------------------------------------------------------

# (a) A real GloriaFood-powered homepage: contains fbgcdn.com CDN asset, the
# ewm2.js script, and both data-glf-ruid / data-glf-cuid attributes.
# Expected: match_strength >= 2 (at least fbgcdn.com + data-glf-ruid), ruid
# captured via id_extractors.
GLORIAFOOD_HTML = (
    '<html>'
    '<head>'
    '<title>Mario\'s Restaurant</title>'
    '<meta property="og:site_name" content="Mario\'s Restaurant">'
    '</head>'
    '<body>'
    '<script src="https://fbgcdn.com/embedder/js/ewm2.js">'
    '</script>'
    '<div'
    ' data-glf-cuid="cafe0000-cafe-cafe-cafe-cafe00000001"'
    ' data-glf-ruid="abcd1234-ab12-ab12-ab12-abcd12345678">'
    '</div>'
    '<a href="mailto:info@marios.com">Email us</a>'
    '</body>'
    '</html>'
)

# (b) A homepage that was surfaced via urlscan but does NOT embed any GloriaFood
# technology.  The page has a generic ordering link with no fingerprint tokens
# (no fbgcdn.com, no ewm2.js, no data-glf-cuid/ruid, no "gloriafood").
# INV-12: normalize must return None because zero fingerprints are present.
LINK_ONLY_HTML = (
    '<html>'
    '<head><title>Acme Burgers</title></head>'
    '<body>'
    '<p>Order via our <a href="https://order.acmefood.com/menu">menu page</a></p>'
    '<a href="mailto:hello@acme.com">Email us</a>'
    '</body>'
    '</html>'
)


# ---------------------------------------------------------------------------
# Helper: in-memory DB seeded with catalog
# ---------------------------------------------------------------------------

def _fresh_session() -> Session:
    """Return a Session backed by an isolated in-memory SQLite DB."""
    engine = init_db("sqlite://")
    session = Session(engine)
    seed_recipes(session)
    return session


# ---------------------------------------------------------------------------
# (a) Multi-signal match strength + id_extractor capture
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_gloriafood_multi_signal_match_strength(self):
        """Canned GloriaFood page → match_strength>=2, matched list, ruid in attributes."""
        adapter = FingerprintDiscoveryAdapter()
        raw = {"host": "marios.com", "recipe_key": "gloriafood"}

        def fake_fetch(url, **_):
            return url, GLORIAFOOD_HTML

        with _fresh_session() as session:
            lead = adapter.normalize(raw, session=session, fetch_fn=fake_fetch)

        assert lead is not None, "Expected a NormalizedLead for a matching homepage"
        assert lead.attributes["match_strength"] >= 2, (
            f"Expected match_strength>=2, got {lead.attributes['match_strength']}"
        )
        matched = lead.attributes["matched"]
        assert isinstance(matched, list), "matched must be a list"
        assert "fbgcdn.com" in matched, (
            f"fbgcdn.com must appear in matched; got {matched}"
        )
        # ruid extractor must have been captured
        assert lead.attributes.get("ruid") is not None, (
            "ruid id_extractor value missing from attributes"
        )
        assert lead.attributes["ruid"] == "abcd1234-ab12-ab12-ab12-abcd12345678"
        assert lead.source_key == "fingerprint"
        assert lead.attributes["recipe_key"] == "gloriafood"
        assert lead.attributes["tech_type"] == "GloriaFood"

    # (b) INV-12: homepage with no fingerprint tokens → None
    def test_link_only_homepage_returns_none(self):
        """Page with no fingerprint tokens → normalize returns None (INV-12)."""
        adapter = FingerprintDiscoveryAdapter()
        raw = {"host": "acmefood.com", "recipe_key": "gloriafood"}

        def fake_fetch(url, **_):
            return url, LINK_ONLY_HTML

        with _fresh_session() as session:
            result = adapter.normalize(raw, session=session, fetch_fn=fake_fetch)

        assert result is None, (
            "INV-12 violated: page with no fingerprint tokens must return None"
        )

    def test_no_html_returns_none(self):
        """fetch returning (None, None) → normalize returns None."""
        adapter = FingerprintDiscoveryAdapter()
        raw = {"host": "broken.com", "recipe_key": "gloriafood"}

        def fake_fetch(url, **_):
            return None, None

        with _fresh_session() as session:
            result = adapter.normalize(raw, session=session, fetch_fn=fake_fetch)

        assert result is None

    def test_disabled_recipe_in_normalize_returns_none(self):
        """normalize with a greyed (disabled) recipe_key returns None."""
        adapter = FingerprintDiscoveryAdapter()
        # "wordpress" is greyed (enabled=False) in the catalog
        raw = {"host": "some-wp-site.com", "recipe_key": "wordpress"}

        def fake_fetch(url, **_):
            return url, "<html><body>wp-content/themes/test</body></html>"

        with _fresh_session() as session:
            result = adapter.normalize(raw, session=session, fetch_fn=fake_fetch)

        assert result is None, (
            "normalize must return None for a disabled/greyed recipe"
        )


# ---------------------------------------------------------------------------
# (c) discover: enabled recipe yields hosts; disabled recipe is skipped
# ---------------------------------------------------------------------------

class TestDiscover:
    def test_discover_yields_hosts_for_enabled_recipe(self):
        """discover_fn returning hosts → adapter yields {host, recipe_key} dicts."""
        adapter = FingerprintDiscoveryAdapter()
        query = AdapterQuery(
            area={}, categories=[], extra={"recipe_key": "gloriafood"}
        )
        called_with: list = []

        def fake_discover(recipe):
            called_with.append(recipe.id)
            return ["marios.com", "joes-pizza.com"]

        with _fresh_session() as session:
            results = list(
                adapter.discover(query, session=session, discover_fn=fake_discover)
            )

        assert called_with == ["gloriafood"], (
            f"discover_fn should have been called with gloriafood recipe; got {called_with}"
        )
        assert len(results) == 2
        assert results[0] == {"host": "marios.com", "recipe_key": "gloriafood"}
        assert results[1] == {"host": "joes-pizza.com", "recipe_key": "gloriafood"}

    def test_discover_skips_disabled_recipe(self):
        """discover with a greyed recipe_key (enabled=False) → yields nothing, discover_fn not called."""
        adapter = FingerprintDiscoveryAdapter()
        # "wordpress" is greyed (enabled=False, confidence="low") in the catalog
        query = AdapterQuery(
            area={}, categories=[], extra={"recipe_key": "wordpress"}
        )

        def fake_discover(recipe):
            pytest.fail("discover_fn must NOT be called for a disabled recipe")
            return []

        with _fresh_session() as session:
            results = list(
                adapter.discover(query, session=session, discover_fn=fake_discover)
            )

        assert results == [], "Expected no results for a disabled/greyed recipe"

    def test_discover_all_enabled_by_category(self):
        """discover with category filter yields hosts from all enabled recipes in that category."""
        adapter = FingerprintDiscoveryAdapter()
        query = AdapterQuery(
            area={}, categories=[],
            extra={"category": "Online Ordering / Restaurants"},
        )
        seen_recipe_keys: list[str] = []

        def fake_discover(recipe):
            seen_recipe_keys.append(recipe.id)
            return [f"{recipe.id}-host.com"]

        with _fresh_session() as session:
            results = list(
                adapter.discover(query, session=session, discover_fn=fake_discover)
            )

        # At minimum "gloriafood" and "chownow" are enabled in this category
        assert "gloriafood" in seen_recipe_keys
        assert "chownow" in seen_recipe_keys
        assert len(results) >= 2
        # Each result carries the right recipe_key
        for r in results:
            assert "host" in r and "recipe_key" in r
