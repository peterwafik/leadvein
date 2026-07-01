"""Shared helper for pipeline-integration tests (used by test_quality_stamp.py)."""
from __future__ import annotations

from sqlmodel import Session, select

from app.core.db import init_db, Lead
from app.core.taxonomy import seed_taxonomy
from app.adapters.base import SourceMeta, AdapterQuery, NormalizedLead
from app.scoring.profiles.utility_energy import UtilityEnergyProfile
from app.scoring.profiles import registry as profile_registry
from app.ingestion.pipeline import ingest


class _FakeAdapter:
    meta = SourceMeta(key="fake_src_h", name="Fake", type="test", url="http://x",
                      license="TESTLIC")

    def discover(self, query):
        return [{"n": "Acme Diner", "site": "https://acmediner.com", "cat": "restaurant",
                 "email": "info@acmediner.com"}]

    def normalize(self, raw):
        return NormalizedLead(
            business_name=raw["n"],
            category_keys=[raw["cat"]],
            address={"city": "London", "line1": "1 High St", "lat": 51.5, "lon": -0.1},
            website_url=raw["site"],
            phone="+44 7911 123456",
            public_email=raw["email"],
            source_key=self.meta.key,
            source_license=self.meta.license,
            raw_ref=raw["n"],
        )

    def attribution(self):
        return "fake attribution"


def _fake_enrich(lead, **kw):
    return {"website_reachable": True, "last_scanned": "2026-06-28T00:00:00+00:00"}


def run_fake_ingest():
    """Run a minimal ingest and return the stored Lead (in-memory DB)."""
    engine = init_db("sqlite://")
    if "utility_energy" not in profile_registry._PROFILES:
        profile_registry.register(UtilityEnergyProfile())
    with Session(engine) as s:
        seed_taxonomy(s)
        ingest(s, _FakeAdapter(), AdapterQuery(area={"city": "London"}, categories=["restaurant"]),
               scoring_profile_key="utility_energy", enrich_fn=_fake_enrich)
        lead = s.exec(select(Lead)).first()
        # Detach: refresh scalars so they survive session close
        s.expunge(lead)
        return lead
