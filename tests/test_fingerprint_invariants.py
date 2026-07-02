"""INV-11..15 — invariants proving fingerprint-sourced leads keep the honesty
spine + accuracy discipline.

INV-11  business-entity only:  NormalizedLead from fingerprint normalization
        carries only business-entity fields; no obviously-personal field.
INV-12  own-homepage (re-assert): page with no fingerprint tokens → None; page
        with tokens → NormalizedLead.
INV-13  multi-signal + grey:   match_strength=1 excluded by min_strength=2;
        a greyed/disabled recipe is NOT run by FingerprintDiscoveryAdapter.discover.
INV-14  dedup:                 one business from OSM + fingerprint → ONE Lead
        with merged per-field provenance (mirrors test_fingerprint_ingest_dedup).
INV-15  sync license / custom: all seeded catalog rows are source=="custom";
        seed_recipes makes NO network call (no live Wappalyzer sync).
grep-clean core:               vendor/fingerprint strings absent from app/core/**/*.py
        (mirrors test_fingerprint_grepclean — asserted here for self-containment).
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
import re

import pytest
from sqlmodel import Session, select

import app.fingerprints.models  # noqa — register table before init_db
from app.adapters.base import AdapterQuery, NormalizedLead
from app.adapters.providers.fingerprint_discovery import FingerprintDiscoveryAdapter
from app.core.db import Lead, init_db
from app.core.targeting.view import lead_view
from app.fingerprints.catalog import CUSTOM_RECIPES
from app.fingerprints.library import list_recipes, seed_recipes
from app.ingestion.pipeline import merge_or_create
from app.targeting.predicates.webpresence import RUNS_TECH


# ---------------------------------------------------------------------------
# Shared HTML fixtures
# ---------------------------------------------------------------------------

# Full GloriaFood-powered homepage: fbgcdn.com CDN asset, ewm2.js script,
# data-glf-ruid / data-glf-cuid attributes.  Expected: match_strength >= 2.
GLORIAFOOD_HTML = (
    "<html>"
    "<head>"
    "<title>Mario's Restaurant</title>"
    '<meta property="og:site_name" content="Mario\'s Restaurant">'
    "</head>"
    "<body>"
    '<script src="https://fbgcdn.com/embedder/js/ewm2.js"></script>'
    "<div"
    ' data-glf-cuid="cafe0000-cafe-cafe-cafe-cafe00000001"'
    ' data-glf-ruid="abcd1234-ab12-ab12-ab12-abcd12345678">'
    "</div>"
    '<a href="mailto:info@marios.com">Email us</a>'
    "</body>"
    "</html>"
)

# Homepage that merely LINKS to a food-ordering URL — no embedded fingerprint.
# INV-12: normalize must return None.
LINK_ONLY_HTML = (
    "<html>"
    "<head><title>Acme Burgers</title></head>"
    "<body>"
    '<p>Order via our <a href="https://order.acmefood.com/menu">menu page</a></p>'
    "</body>"
    "</html>"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_session() -> Session:
    """Return a Session backed by an isolated in-memory SQLite DB seeded with
    the fingerprint catalog (idempotent upsert)."""
    engine = init_db("sqlite://")
    session = Session(engine)
    seed_recipes(session)
    return session


# Set of field-name substrings that would indicate a personal-identity field
# was accidentally added to the NormalizedLead or its attributes.
_PERSONAL_FIELD_NAMES = frozenset({
    "person_name", "first_name", "last_name", "surname", "forename",
    "contact_name", "contact_person", "full_name",
    "job_title", "title",
    "personal_email", "personal_phone", "personal_contact",
})


# ---------------------------------------------------------------------------
# INV-11: business-entity only
# ---------------------------------------------------------------------------

class TestINV11BusinessEntityOnly:
    """INV-11: Fingerprint normalization never populates personal-identity fields."""

    def test_normalized_lead_class_has_no_personal_fields(self):
        """NormalizedLead dataclass must not define any personal-identity fields."""
        field_names = {f.name for f in dataclasses.fields(NormalizedLead)}
        leaked = field_names & _PERSONAL_FIELD_NAMES
        assert leaked == set(), (
            f"NormalizedLead carries personal field(s): {leaked!r}. "
            "Only business-entity fields are permitted on the normalized data structure."
        )

    def test_fingerprint_attrs_contain_no_personal_keys(self):
        """Normalizing a GloriaFood page must not produce personal keys in attributes."""
        adapter = FingerprintDiscoveryAdapter()
        raw = {"host": "marios.com", "recipe_key": "gloriafood"}

        def fake_fetch(url, **_):
            return url, GLORIAFOOD_HTML

        with _fresh_session() as session:
            lead = adapter.normalize(raw, session=session, fetch_fn=fake_fetch)

        assert lead is not None, "Expected a NormalizedLead from a matching homepage"

        attr_keys = set((lead.attributes or {}).keys())
        leaked = attr_keys & _PERSONAL_FIELD_NAMES
        assert leaked == set(), (
            f"INV-11: attributes dict contains personal field(s): {leaked!r}"
        )

    def test_fingerprint_lead_public_email_not_personal_email(self):
        """The contact field on NormalizedLead is 'public_email', not 'personal_email'."""
        # Verify at the class level — personal_email must not be a dataclass field.
        field_names = {f.name for f in dataclasses.fields(NormalizedLead)}
        assert "public_email" in field_names, (
            "NormalizedLead must have a 'public_email' field (business contact)"
        )
        assert "personal_email" not in field_names, (
            "NormalizedLead must NOT have a 'personal_email' field"
        )

    def test_fingerprint_normalize_returns_business_name_not_person_name(self):
        """business_name from fingerprint normalization is a business name, not a person name.

        The GloriaFood fixture contains 'Mario\\'s Restaurant' — a typical
        business entity name.  Normalizing it must populate business_name
        (not a person-named field) and the field must carry a non-empty value.
        """
        adapter = FingerprintDiscoveryAdapter()
        raw = {"host": "marios.com", "recipe_key": "gloriafood"}

        def fake_fetch(url, **_):
            return url, GLORIAFOOD_HTML

        with _fresh_session() as session:
            lead = adapter.normalize(raw, session=session, fetch_fn=fake_fetch)

        assert lead is not None
        assert lead.business_name, "business_name must be populated"
        # source_key must be "fingerprint" — not a personal identifier
        assert lead.source_key == "fingerprint"
        # The lead carries no personal contact source — public_email is the field
        assert hasattr(lead, "public_email")
        assert not hasattr(lead, "personal_email")


# ---------------------------------------------------------------------------
# INV-12: own-homepage confirmation (re-assert)
# ---------------------------------------------------------------------------

class TestINV12OwnHomepage:
    """INV-12: Only the business's OWN embedded fingerprint token qualifies a match."""

    def test_link_only_page_returns_none(self):
        """INV-12: page that LINKS to vendor but has NO embedded tokens → None."""
        adapter = FingerprintDiscoveryAdapter()
        raw = {"host": "acmefood.com", "recipe_key": "gloriafood"}

        def fake_fetch(url, **_):
            return url, LINK_ONLY_HTML

        with _fresh_session() as session:
            result = adapter.normalize(raw, session=session, fetch_fn=fake_fetch)

        assert result is None, (
            "INV-12 violated: a page that only links to a vendor — but does not "
            "embed the fingerprint token — must return None, not a NormalizedLead."
        )

    def test_embedded_fingerprint_page_returns_lead(self):
        """INV-12 (positive): page WITH embedded tokens returns a NormalizedLead."""
        adapter = FingerprintDiscoveryAdapter()
        raw = {"host": "marios.com", "recipe_key": "gloriafood"}

        def fake_fetch(url, **_):
            return url, GLORIAFOOD_HTML

        with _fresh_session() as session:
            result = adapter.normalize(raw, session=session, fetch_fn=fake_fetch)

        assert result is not None, (
            "INV-12 (positive): a page with embedded fingerprint tokens must "
            "return a NormalizedLead, not None."
        )
        assert result.attributes.get("match_strength", 0) >= 1, (
            "Match strength must be at least 1 when at least one fingerprint token is found."
        )

    def test_no_html_returns_none(self):
        """fetch returning (None, None) → normalize returns None."""
        adapter = FingerprintDiscoveryAdapter()
        raw = {"host": "broken.com", "recipe_key": "gloriafood"}

        def fake_fetch(url, **_):
            return None, None

        with _fresh_session() as session:
            result = adapter.normalize(raw, session=session, fetch_fn=fake_fetch)

        assert result is None, "Absent HTML must always yield None."


# ---------------------------------------------------------------------------
# INV-13: multi-signal strength filter + greyed recipe skip
# ---------------------------------------------------------------------------

def _strength_view(recipe_key: str, match_strength: int) -> dict:
    """Build a lead_view dict carrying the given recipe_key and match_strength."""
    attrs = {"recipe_key": recipe_key, "match_strength": match_strength}
    return lead_view(Lead(
        city="London", country="GB",
        phone="", public_email="",
        score_total=50,
        attributes_json=json.dumps(attrs),
        intent_json="{}", subscores_json="{}", category_keys_json="[]",
    ))


class TestINV13MultiSignalAndGrey:
    """INV-13: strength filter drops weak-signal leads; greyed recipes are skipped."""

    def test_strength_1_excluded_by_min_strength_2(self):
        """INV-13: match_strength=1 is excluded by a min_strength=2 filter."""
        view = _strength_view("gloriafood", 1)
        result = RUNS_TECH.matches(view, {"recipe_in": ["gloriafood"], "min_strength": 2})
        assert result is False, (
            "INV-13: a lead with match_strength=1 must be excluded (False) when "
            "the filter requires min_strength=2."
        )

    def test_strength_2_passes_min_strength_2(self):
        """INV-13 (positive): match_strength=2 passes a min_strength=2 filter."""
        view = _strength_view("gloriafood", 2)
        result = RUNS_TECH.matches(view, {"recipe_in": ["gloriafood"], "min_strength": 2})
        assert result is True, (
            "INV-13: match_strength=2 must pass (True) when min_strength=2."
        )

    def test_strength_3_passes_min_strength_2(self):
        """INV-13: match_strength=3 also passes min_strength=2."""
        view = _strength_view("gloriafood", 3)
        result = RUNS_TECH.matches(view, {"recipe_in": ["gloriafood"], "min_strength": 2})
        assert result is True

    def test_greyed_recipe_not_run_by_discover(self):
        """INV-13: a greyed (enabled=False) recipe is NOT run by discover()."""
        adapter = FingerprintDiscoveryAdapter()
        # "wordpress" is greyed (enabled=False, confidence="low") in the catalog.
        query = AdapterQuery(
            area={}, categories=[], extra={"recipe_key": "wordpress"}
        )

        def fake_discover(recipe):
            pytest.fail(
                "INV-13: discover_fn must NOT be called for a disabled/greyed recipe; "
                f"called with recipe.id={recipe.id!r}"
            )
            return []

        with _fresh_session() as session:
            results = list(
                adapter.discover(query, session=session, discover_fn=fake_discover)
            )

        assert results == [], (
            "INV-13: a disabled/greyed recipe must yield zero results from discover."
        )

    def test_enabled_recipe_is_run_by_discover(self):
        """INV-13 (positive): an enabled recipe IS run by discover()."""
        adapter = FingerprintDiscoveryAdapter()
        query = AdapterQuery(
            area={}, categories=[], extra={"recipe_key": "gloriafood"}
        )
        called: list[str] = []

        def fake_discover(recipe):
            called.append(recipe.id)
            return ["marios.com"]

        with _fresh_session() as session:
            results = list(
                adapter.discover(query, session=session, discover_fn=fake_discover)
            )

        assert called == ["gloriafood"], (
            "INV-13: discover_fn must be called exactly once for the enabled recipe."
        )
        assert len(results) == 1
        assert results[0] == {"host": "marios.com", "recipe_key": "gloriafood"}


# ---------------------------------------------------------------------------
# INV-14: dedup — one business, two sources, one lead
# ---------------------------------------------------------------------------

_OSM_KEY = "osm"
_OSM_LIC = "ODbL"
_FP_KEY = "fingerprint"
_FP_LIC = "Detected from public page source via urlscan.io index (recipe: GloriaFood)"

VALID_PHONE = "+44 7911 123456"  # valid UK mobile — phonenumbers.is_valid_number == True


def _osm_normalized(domain: str) -> NormalizedLead:
    """OSM-style lead: address + category, a website domain, no phone."""
    return NormalizedLead(
        business_name="Test Pizza",
        category_keys=["restaurant"],
        address={
            "line1": "123 High St",
            "city": "London",
            "postal_code": "SW1A 1AA",
            "country": "GB",
            "lat": 51.5,
            "lon": -0.1,
        },
        website_url=f"https://{domain}",
        phone="",
        public_email="",
        source_key=_OSM_KEY,
        source_license=_OSM_LIC,
    )


def _fp_normalized(domain: str) -> NormalizedLead:
    """Fingerprint-detection-style lead: website + contact + recipe attributes."""
    return NormalizedLead(
        business_name="Test Pizza",
        category_keys=[],
        address={"country": "GB"},
        website_url=f"https://{domain}",
        phone=VALID_PHONE,
        public_email="info@testpizza.co.uk",
        attributes={
            "recipe_key": "gloriafood",
            "matched": ["fbgcdn.com", "ewm2.js"],
            "match_strength": 2,
            "tech_type": "GloriaFood",
        },
        source_key=_FP_KEY,
        source_license=_FP_LIC,
    )


class TestINV14Dedup:
    """INV-14: same business from OSM + fingerprint → ONE Lead, merged provenance."""

    def test_one_business_two_sources_produces_one_lead(self):
        """OSM + fingerprint ingest of the same domain → ONE Lead row, not two."""
        engine = init_db("sqlite://")
        with Session(engine) as session:
            domain = "inv14-pizza.co.uk"

            # Step 1: ingest via OSM
            osm_n = _osm_normalized(domain)
            osm_lead = merge_or_create(session, osm_n, source_key=_OSM_KEY, license=_OSM_LIC)
            session.commit()
            session.refresh(osm_lead)
            osm_id = osm_lead.id

            # Sanity: one row, no phone yet
            all_leads = session.exec(select(Lead)).all()
            assert len(all_leads) == 1
            assert all_leads[0].phone == ""

            # Step 2: fingerprint source finds the same domain
            fp_n = _fp_normalized(domain)
            merged = merge_or_create(session, fp_n, source_key=_FP_KEY, license=_FP_LIC)
            session.commit()
            session.refresh(merged)

            # Must still be ONE lead (not two)
            all_leads = session.exec(select(Lead)).all()
            assert len(all_leads) == 1, (
                f"INV-14: expected 1 lead after cross-source merge, got {len(all_leads)}"
            )
            assert merged.id == osm_id, (
                "INV-14: merge_or_create must return the existing OSM lead, not create a new row"
            )

            # Phone from fingerprint must now be filled
            assert merged.phone == VALID_PHONE

            # Per-field provenance
            prov = json.loads(merged.field_provenance_json)
            assert prov.get("address_line1", {}).get("source") == _OSM_KEY, (
                f"INV-14: address_line1 must be attributed to osm; got {prov.get('address_line1')}"
            )
            assert prov.get("city", {}).get("source") == _OSM_KEY, (
                f"INV-14: city must be attributed to osm; got {prov.get('city')}"
            )
            assert prov.get("phone", {}).get("source") == _FP_KEY, (
                f"INV-14: phone must be attributed to fingerprint; got {prov.get('phone')}"
            )

            # Tech attributes must be merged — including recipe_key and match_strength
            attrs = json.loads(merged.attributes_json)
            assert attrs.get("recipe_key") == "gloriafood", (
                f"INV-14: attributes.recipe_key missing or wrong: {attrs}"
            )
            assert attrs.get("match_strength") == 2
            assert prov.get("attributes.recipe_key", {}).get("source") == _FP_KEY, (
                "INV-14: attributes.recipe_key provenance must point to the fingerprint source"
            )

    def test_osm_address_not_overwritten_by_fingerprint(self):
        """INV-14 waterfall: OSM address fields must survive a fingerprint re-ingest."""
        engine = init_db("sqlite://")
        with Session(engine) as session:
            domain = "inv14-waterfall.co.uk"

            # First: OSM with London
            merge_or_create(
                session, _osm_normalized(domain),
                source_key=_OSM_KEY, license=_OSM_LIC,
            )
            session.commit()

            # Fingerprint attempts to supply a different city — waterfall must block it
            fp_n = NormalizedLead(
                business_name="Test Pizza",
                category_keys=[],
                address={"city": "Manchester"},  # different city — must be ignored
                website_url=f"https://{domain}",
                phone=VALID_PHONE,
                public_email="",
                source_key=_FP_KEY,
                source_license=_FP_LIC,
            )
            merged = merge_or_create(session, fp_n, source_key=_FP_KEY, license=_FP_LIC)
            session.commit()
            session.refresh(merged)

            assert merged.city == "London", (
                f"INV-14 waterfall: OSM city 'London' must not be overwritten by "
                f"fingerprint source; got {merged.city!r}"
            )


# ---------------------------------------------------------------------------
# INV-15: sync license / custom-only catalog
# ---------------------------------------------------------------------------

class TestINV15CustomOnly:
    """INV-15: catalog is custom-only; no live-sync code path runs at seed time."""

    def test_all_catalog_entries_are_custom(self):
        """Every entry in CUSTOM_RECIPES must have source='custom'."""
        non_custom = [r for r in CUSTOM_RECIPES if r.get("source") != "custom"]
        assert non_custom == [], (
            "INV-15: non-custom catalog entries found: "
            f"{[(r['recipe_key'], r.get('source')) for r in non_custom]}. "
            "Wappalyzer-synced rows are deferred (license-gated) and must not "
            "appear in the current increment."
        )

    def test_seeded_db_rows_are_custom(self):
        """All rows seeded into a fresh in-memory DB must have source='custom'."""
        with _fresh_session() as session:
            rows = list_recipes(session)
            assert rows, "Expected at least one seeded catalog row"
            non_custom = [r for r in rows if r.source != "custom"]
            assert non_custom == [], (
                "INV-15: non-custom rows in seeded DB: "
                f"{[(r.recipe_key, r.source) for r in non_custom]}"
            )

    def test_seed_recipes_makes_no_network_calls(self, monkeypatch):
        """INV-15: seed_recipes must not perform any HTTP request.

        If this assertion fires, a live Wappalyzer sync (or any other network
        call) was introduced into the seeding path — which is not licensed for
        the current increment.
        """
        import requests

        def _no_network(*args, **kwargs):
            raise AssertionError(
                "INV-15: seed_recipes triggered a network call via requests; "
                f"args={args!r}. No live-sync is permitted in the seeding path."
            )

        monkeypatch.setattr(requests, "get", _no_network)
        monkeypatch.setattr(requests, "post", _no_network)
        monkeypatch.setattr(requests, "request", _no_network)

        engine = init_db("sqlite://")
        with Session(engine) as session:
            count = seed_recipes(session)

        assert count == len(CUSTOM_RECIPES), (
            f"INV-15: seed_recipes returned {count} but CUSTOM_RECIPES has "
            f"{len(CUSTOM_RECIPES)} entries."
        )

    def test_seeded_rows_have_no_synced_at(self):
        """Seeded rows must have synced_at=None — not populated by any live sync."""
        with _fresh_session() as session:
            rows = list_recipes(session)
            synced = [r for r in rows if r.synced_at is not None]
            assert synced == [], (
                "INV-15: rows with synced_at populated found after seed — "
                "indicates a live-sync code path ran: "
                f"{[(r.recipe_key, r.synced_at) for r in synced]!r}"
            )

    def test_seed_is_idempotent_and_custom_only(self):
        """seed_recipes called twice must not add new rows or change source to non-custom."""
        with _fresh_session() as session:
            count_first = seed_recipes(session)
            count_second = seed_recipes(session)
            rows = list_recipes(session)

        assert count_first == count_second == len(CUSTOM_RECIPES)
        assert all(r.source == "custom" for r in rows), (
            "INV-15: a second seed call must not introduce non-custom rows"
        )


# ---------------------------------------------------------------------------
# grep-clean core (mirrors test_fingerprint_grepclean — self-contained)
# ---------------------------------------------------------------------------

def test_inv_grep_clean_core():
    """INV grep gate: vendor/fingerprint strings must not appear in app/core/**/*.py.

    This mirrors test_fingerprint_grepclean.test_core_is_fingerprint_grep_clean.
    Including it here ensures the invariants test file is self-contained:
    any core-level leak is caught by BOTH test files.

    If a real hit is found the offending string must be RELOCATED out of core
    (to app/fingerprints/ or the appropriate adapter module) — do NOT weaken
    this assertion.
    """
    root = pathlib.Path("app/core")
    pat = re.compile(
        r"gloriafood|chownow|shopify|fbgcdn|ewm2|data-glf|wappalyzer|urlscan|publicwww",
        re.I,
    )
    hits: list[str] = []
    for p in root.rglob("*.py"):
        for i, line in enumerate(
            p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            if pat.search(line):
                hits.append(f"{p}:{i}: {line.strip()}")

    assert hits == [], (
        "INV grep-clean: vendor/fingerprint strings leaked into app/core/**/*.py.\n"
        "Relocate the offending string(s) to app/fingerprints/ or an adapter module:\n"
        + "\n".join(hits)
    )
