"""
Tests that the ingest pipeline stamps Lead.country from the pull context
when the OSM addr:country tag is absent, and that OSM tag wins when present.
"""
from sqlmodel import Session, select

from app.core.db import init_db, Lead
from app.core.taxonomy import seed_taxonomy
from app.adapters.base import SourceMeta, AdapterQuery, NormalizedLead
from app.scoring.profiles.utility_energy import UtilityEnergyProfile
from app.scoring.profiles import registry as profile_registry
from app.ingestion.pipeline import ingest


class _NodeAdapter:
    """Fake adapter that yields one node; address dict is supplied at construction."""

    meta = SourceMeta(key="country_test_src", name="CountryTest", type="test",
                      url="http://x", license="TESTLIC")

    def __init__(self, address: dict):
        self._address = address

    def discover(self, query):
        return [{"n": "Test Biz", "site": "https://testbiz.example.com"}]

    def normalize(self, raw):
        return NormalizedLead(
            business_name=raw["n"],
            category_keys=["restaurant"],
            address=self._address,
            website_url=raw["site"],
            source_key=self.meta.key,
            source_license=self.meta.license,
            raw_ref=raw["n"],
        )

    def attribution(self):
        return "test attribution"


def _fake_enrich(lead, **kw):
    return {
        "website_reachable": False, "ssl": False, "online_ordering_detected": False,
        "booking_detected": False, "payment_provider_detected": False,
        "ecommerce_detected": False, "last_scanned": "2026-06-28T00:00:00+00:00",
    }


def _run(adapter, query):
    engine = init_db("sqlite://")
    profile_registry.register(UtilityEnergyProfile())
    with Session(engine) as s:
        seed_taxonomy(s)
        ingest(s, adapter, query, scoring_profile_key="utility_energy",
               enrich_fn=_fake_enrich)
        leads = s.exec(select(Lead)).all()
        assert leads, "Expected one Lead to be stored"
        return leads[0].country


def test_pull_country_used_when_osm_tag_absent():
    """No addr:country in OSM node → Lead.country should come from query.country."""
    adapter = _NodeAdapter(address={"city": "Oxford"})
    query = AdapterQuery(area={"city": "Oxford"}, categories=["restaurant"], country="GB")
    assert _run(adapter, query) == "GB"


def test_osm_tag_wins_over_pull_country():
    """addr:country present in OSM node → OSM value wins; query.country is ignored."""
    adapter = _NodeAdapter(address={"city": "New York", "country": "US"})
    query = AdapterQuery(area={"city": "New York"}, categories=["restaurant"], country="GB")
    assert _run(adapter, query) == "US"


def test_no_country_anywhere_gives_empty():
    """Neither OSM tag nor query.country set → Lead.country is empty string."""
    adapter = _NodeAdapter(address={"city": "Somewhere"})
    query = AdapterQuery(area={"city": "Somewhere"}, categories=["restaurant"])
    assert _run(adapter, query) == ""
