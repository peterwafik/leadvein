"""Tests covering FIX 1, FIX 3, and FIX 4 of the fingerprint-primary-source branch.

FIX 1(a): fingerprint adapter excluded from generic ingest dropdown/runner.
FIX 1(b): POST /admin/recipes/{key}/run ingests via ingest_normalized (injected
          discover/fetch); hot lead surfaces through gate, cold is held; dedup works.
FIX 3:    Bare-vendor tokens removed from enabled recipes — a homepage that merely
          LINKS the vendor (no asset-domain embed) → normalize returns None;
          a homepage that loads the asset domain → match.
FIX 4:    belt-and-suspenders vendor exclusion in normalize: host that matches
          recipe.exclude_hosts → None, independent of discover filtering.

NO live network calls in any test.
"""
from __future__ import annotations

import json

import pytest
from sqlmodel import Session, select

import app.fingerprints.models  # noqa — register table before init_db
from app.adapters.base import AdapterQuery
from app.adapters.providers.fingerprint_discovery import FingerprintDiscoveryAdapter
from app.core.db import Lead, init_db
from app.core.serve_filters import register_serve_filter, passes_serve_filters
from app.core.serve_filters import clear as _clear_filters
from app.fingerprints.library import seed_recipes, get_recipe, promote_recipe
from app.quality.serve_gate import quality_serve_filter
from app.web.routes_admin import _generic_ingest_keys, _run_recipe_for_admin


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

VALID_PHONE = "+44 7911 123456"  # valid UK mobile


def _fresh_session() -> Session:
    engine = init_db("sqlite://")
    session = Session(engine)
    seed_recipes(session)
    return session


# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

# A homepage that loads the Shopify CDN (distinctive asset domain) — should match.
SHOPIFY_CDN_HTML = (
    "<html><head><title>Great Shop</title></head>"
    "<body>"
    '<script src="https://cdn.shopify.com/s/files/1/0001/shop.js"></script>'
    "<p>Welcome to our store.</p>"
    "</body></html>"
)

# A homepage that ONLY mentions Shopify in a link (no CDN embed) — must NOT match.
SHOPIFY_LINK_ONLY_HTML = (
    "<html><head><title>Blog Post</title></head>"
    "<body>"
    "<p>We use <a href=\"https://www.shopify.com/\">Shopify</a> for our store.</p>"
    "</body></html>"
)

# A homepage with a valid phone embedded — used to create a hot fingerprint lead.
HOT_LEAD_HTML = (
    "<html><head><title>Hot Pizza</title>"
    '<meta property="og:site_name" content="Hot Pizza">'
    "</head><body>"
    '<script src="https://fbgcdn.com/embedder/js/ewm2.js"></script>'
    '<div data-glf-cuid="cafe-1" data-glf-ruid="abcd-1234"></div>'
    f"<a href=\"tel:{VALID_PHONE}\">Call us</a>"
    "</body></html>"
)

# A homepage that matches the fingerprint but has NO contact details — cold lead.
COLD_LEAD_HTML = (
    "<html><head><title>Cold Cafe</title>"
    '<meta property="og:site_name" content="Cold Cafe">'
    "</head><body>"
    '<script src="https://fbgcdn.com/embedder/js/ewm2.js"></script>'
    '<div data-glf-cuid="cafe-2" data-glf-ruid="efgh-5678"></div>'
    "</body></html>"
)


# ===========================================================================
# FIX 1(a): fingerprint adapter excluded from generic ingest
# ===========================================================================

class TestFix1aGenericIngestExclusion:
    """Fingerprint adapter must not appear in / be accepted by generic ingest."""

    def test_fingerprint_key_not_in_generic_ingest_keys(self, monkeypatch):
        """_generic_ingest_keys() must not include the fingerprint adapter key."""
        import app.adapters.providers as prov
        # Ensure fingerprint adapter is registered
        prov.register_providers()

        keys = _generic_ingest_keys()
        assert "fingerprint" not in keys, (
            f"'fingerprint' must NOT appear in generic ingest keys; got {keys}"
        )

    def test_generic_ingest_post_with_fingerprint_key_rejected(self):
        """POST /admin/ingest with adapter_key='fingerprint' → clean rejection (not 500)."""
        import re
        from fastapi.testclient import TestClient
        import app.leadvault as lv

        c = TestClient(lv.app)
        # Log in as admin
        login_page = c.get("/login").text
        m = re.search(r'name="csrf_token" value="([^"]+)"', login_page)
        token = m.group(1) if m else ""
        c.post("/login", data={"email": "admin@leadvault.local",
                               "password": "admin12345", "csrf_token": token})

        r = c.post("/admin/ingest", data={
            "adapter_key": "fingerprint",
            "city": "London",
            "categories": "",
            "scoring_profile_key": "utility_energy",
            "csrf_token": token,
        })
        # Must NOT be a 500; either 200 (error page) or 4xx
        assert r.status_code != 500, (
            "POST /admin/ingest with fingerprint adapter must not 500; "
            f"got {r.status_code}"
        )
        # Response should contain an error message, not raw exception text
        assert "TypeError" not in r.text, (
            "Response must not expose Python TypeError from missing session argument"
        )


# ===========================================================================
# FIX 1(b): dedicated recipe run route
# ===========================================================================

class TestFix1bRecipeRun:
    """_run_recipe_for_admin with injected discover/fetch — no live network."""

    def _fake_discover(self, recipe):
        """Return two fake hosts: one hot (with phone in HTML), one cold (no phone)."""
        return ["hotpizza-fix1.co.uk", "coldcafe-fix1.co.uk"]

    def _fake_fetch(self, url, **_):
        """Return HOT_LEAD_HTML for the first host, COLD_LEAD_HTML for the second."""
        if "hotpizza" in url:
            return url, HOT_LEAD_HTML
        return url, COLD_LEAD_HTML

    def test_run_recipe_stores_leads(self):
        """Both hot and cold leads are stored by ingest_normalized."""
        with _fresh_session() as session:
            result = _run_recipe_for_admin(
                session, "gloriafood",
                discover_fn=self._fake_discover,
                fetch_fn=self._fake_fetch,
            )
        assert "error" not in result, f"Expected success; got error: {result.get('error')}"
        assert result.get("normalized", 0) == 2, (
            f"Expected 2 normalised leads; got {result}"
        )
        assert result.get("stored", 0) == 2, (
            f"Expected 2 stored leads; got {result}"
        )

    def test_run_recipe_hot_lead_surfaces_cold_is_held(self):
        """Hot lead (valid phone) passes quality gate; cold (no contact) is held."""
        _clear_filters()
        register_serve_filter(quality_serve_filter)
        try:
            with _fresh_session() as session:
                _run_recipe_for_admin(
                    session, "gloriafood",
                    discover_fn=self._fake_discover,
                    fetch_fn=self._fake_fetch,
                )
                leads = session.exec(select(Lead)).all()
                assert len(leads) == 2

                hot = next(
                    (l for l in leads if l.phone and l.phone.replace(" ", "") != ""),
                    None,
                )
                cold = next(
                    (l for l in leads if not l.phone or l.phone.strip() == ""),
                    None,
                )
                assert hot is not None, "Expected a hot lead with phone"
                assert cold is not None, "Expected a cold lead without phone"

                # Hot lead passes the quality gate
                assert passes_serve_filters(session, buyer_account_id=1, lead=hot), (
                    "Hot fingerprint lead (valid phone) must surface through quality gate"
                )
                # Cold lead is held by the quality gate
                assert not passes_serve_filters(session, buyer_account_id=1, lead=cold), (
                    "Cold fingerprint lead (no contact) must be held by quality gate"
                )
        finally:
            _clear_filters()

    def test_run_recipe_dedup_on_second_run(self):
        """Running the same recipe twice merges leads — no duplicates created."""
        with _fresh_session() as session:
            # First run — stores 2 leads
            _run_recipe_for_admin(
                session, "gloriafood",
                discover_fn=self._fake_discover,
                fetch_fn=self._fake_fetch,
            )
            leads_after_first = session.exec(select(Lead)).all()
            assert len(leads_after_first) == 2

            # Second run — same hosts; merge_or_create should not create new rows
            _run_recipe_for_admin(
                session, "gloriafood",
                discover_fn=self._fake_discover,
                fetch_fn=self._fake_fetch,
            )
            leads_after_second = session.exec(select(Lead)).all()
            assert len(leads_after_second) == 2, (
                "Second run must not create duplicate lead rows; "
                f"expected 2 leads, got {len(leads_after_second)}"
            )

    def test_run_disabled_recipe_returns_error(self):
        """Running a disabled/greyed recipe returns an error dict, not a crash."""
        with _fresh_session() as session:
            result = _run_recipe_for_admin(
                session, "wordpress",  # greyed in catalog
                discover_fn=self._fake_discover,
                fetch_fn=self._fake_fetch,
            )
        assert "error" in result, (
            f"Running a disabled recipe must return an error dict; got {result}"
        )


# ===========================================================================
# FIX 3: INV-12 extended to non-gloriafood enabled recipe (shopify)
# ===========================================================================

class TestFix3DistinctiveAssetDomainRequired:
    """INV-12 extended: pages that merely mention/link the vendor (no CDN embed) → None."""

    def test_shopify_link_only_returns_none(self):
        """Shopify: page that LINKS to shopify.com but does NOT load cdn.shopify.com
        → normalize returns None (INV-12: no asset-domain embed → not a match)."""
        adapter = FingerprintDiscoveryAdapter()
        raw = {"host": "someblog.com", "recipe_key": "shopify"}

        def fake_fetch(url, **_):
            return url, SHOPIFY_LINK_ONLY_HTML

        with _fresh_session() as session:
            result = adapter.normalize(raw, session=session, fetch_fn=fake_fetch)

        assert result is None, (
            "INV-12 (shopify): a page that LINKS to shopify.com but does not "
            "load cdn.shopify.com must return None — bare-vendor token removed "
            "by FIX 3 means only the CDN embed domain qualifies."
        )

    def test_shopify_cdn_embed_returns_lead(self):
        """Shopify: page that loads cdn.shopify.com → normalize returns a NormalizedLead."""
        adapter = FingerprintDiscoveryAdapter()
        raw = {"host": "greatshop.co.uk", "recipe_key": "shopify"}

        def fake_fetch(url, **_):
            return url, SHOPIFY_CDN_HTML

        with _fresh_session() as session:
            result = adapter.normalize(raw, session=session, fetch_fn=fake_fetch)

        assert result is not None, (
            "INV-12 (shopify positive): a page that loads cdn.shopify.com must "
            "return a NormalizedLead — asset-domain token present."
        )
        assert result.attributes.get("match_strength", 0) >= 1

    def test_enabled_recipe_has_no_bare_vendor_name_tokens(self):
        """All HIGH-CONFIDENCE (enabled) recipes must have no bare vendor-name token
        that could match a mere textual mention or outbound link.

        'Bare' means the token is identical to the vendor's brand name and is not
        a subdomain or distinctive path (e.g. 'shopify', 'calendly', 'hubspot').
        Distinctive tokens like 'cdn.shopify.com', 'assets.calendly.com',
        'hs-scripts', 'zdassets', 'driftt' are allowed.
        """
        import json as _json
        from app.fingerprints.catalog import CUSTOM_RECIPES

        # Tokens that are bare vendor brand names (single-word, no '.' or '-' from CDN)
        # A token is considered "bare" if it is a lowercase single word with no dots
        # and it matches a trivially-mentionable vendor name.
        KNOWN_BARE_TOKENS = {
            "shopify", "wix", "squarespace", "webflow", "duda",
            "calendly", "intercom", "zendesk", "tawkto", "crisp",
            "drift", "freshchat", "livechat", "klaviyo", "hubspot",
            "marketo", "hotjar", "segment", "trustpilot", "yotpo",
            "typeform", "jotform", "klarna", "bigcommerce",
            "chownow",  # greyed but keep assertion to confirm
        }

        violations = []
        for recipe in CUSTOM_RECIPES:
            if not recipe.get("enabled", False):
                continue  # only check enabled recipes
            fps = _json.loads(recipe.get("verify_fingerprints_json", "[]"))
            for fp in fps:
                if fp.lower() in KNOWN_BARE_TOKENS:
                    violations.append(
                        f"recipe={recipe['recipe_key']!r} contains bare token {fp!r}"
                    )

        assert violations == [], (
            "FIX 3: enabled recipes contain bare vendor-name tokens that would "
            "match a mere textual mention (INV-12 violation):\n"
            + "\n".join(violations)
        )


# ===========================================================================
# FIX 4: belt-and-suspenders vendor exclusion in normalize
# ===========================================================================

class TestFix4VendorExclusionInNormalize:
    """normalize must return None if host matches any recipe.exclude_hosts token."""

    def test_vendor_own_domain_excluded_in_normalize(self):
        """normalize returns None when host is the vendor's own domain.

        Even if discover() would never return this host (it filters via
        normalize_hosts), normalize() must independently guard against it.
        """
        adapter = FingerprintDiscoveryAdapter()

        # "shopify.com" would normally be excluded by discover() via exclude_hosts
        # (which contains "shopify"), but we test that normalize() also rejects it.
        raw = {"host": "mystore.shopify.com", "recipe_key": "shopify"}

        def fake_fetch(url, **_):
            # Return HTML with the CDN token so we know the exclusion is from
            # exclude_hosts, not from fingerprint absence
            return url, SHOPIFY_CDN_HTML

        with _fresh_session() as session:
            result = adapter.normalize(raw, session=session, fetch_fn=fake_fetch)

        assert result is None, (
            "FIX 4: normalize must return None for a host matching "
            "recipe.exclude_hosts — vendor's own domain must never be enriched"
        )

    def test_non_vendor_domain_not_excluded(self):
        """normalize returns a lead when host is a non-vendor domain with CDN embed."""
        adapter = FingerprintDiscoveryAdapter()
        raw = {"host": "legitstore.co.uk", "recipe_key": "shopify"}

        def fake_fetch(url, **_):
            return url, SHOPIFY_CDN_HTML

        with _fresh_session() as session:
            result = adapter.normalize(raw, session=session, fetch_fn=fake_fetch)

        assert result is not None, (
            "FIX 4: a legitimate non-vendor domain with CDN embed must NOT be "
            "excluded by the vendor exclusion check"
        )

    def test_gloriafood_own_domain_excluded(self):
        """normalize returns None when host contains 'gloriafood' (in exclude_hosts)."""
        adapter = FingerprintDiscoveryAdapter()
        raw = {"host": "orders.gloriafood.com", "recipe_key": "gloriafood"}

        def fake_fetch(url, **_):
            # HTML does embed fbgcdn.com — exclusion is due to host, not fingerprints
            return url, (
                "<html><body>"
                '<script src="https://fbgcdn.com/embedder/js/ewm2.js"></script>'
                '<div data-glf-ruid="test-ruid-1234" data-glf-cuid="test-cuid-1234">'
                "</div></body></html>"
            )

        with _fresh_session() as session:
            result = adapter.normalize(raw, session=session, fetch_fn=fake_fetch)

        assert result is None, (
            "FIX 4: host 'orders.gloriafood.com' contains 'gloriafood' which is "
            "in exclude_hosts — normalize must return None (vendor's own domain)"
        )
