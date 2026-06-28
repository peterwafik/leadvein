from sqlmodel import Session, select
from app.core.db import init_db, Lead, LeadSource, OptOutRequest, IngestionJob
from app.core.taxonomy import seed_taxonomy
from app.adapters.base import SourceMeta, AdapterQuery, NormalizedLead
from app.scoring.profiles.utility_energy import UtilityEnergyProfile
from app.scoring.profiles import registry as profile_registry
from app.ingestion.pipeline import ingest


class FakeAdapter:
    meta = SourceMeta(key="fake_src", name="Fake", type="test", url="http://x",
                      license="TESTLIC")

    def discover(self, query):
        return [{"n": "Joe Diner", "site": "https://joediner.com", "cat": "restaurant"},
                {"n": "Optout Cafe", "site": "https://optout.com", "cat": "cafe"},
                {"n": "Joe Diner Dup", "site": "https://joediner.com", "cat": "restaurant"}]

    def normalize(self, raw):
        return NormalizedLead(business_name=raw["n"], category_keys=[raw["cat"]],
                              address={"city": "London"}, website_url=raw["site"],
                              phone="+44 20 0000 0000", source_key=self.meta.key,
                              source_license=self.meta.license, raw_ref=raw["n"])

    def attribution(self):
        return "fake attribution"


def _fake_enrich(lead, **kw):
    return {"website_reachable": True, "ssl": True, "online_ordering_detected": True,
            "booking_detected": False, "payment_provider_detected": False,
            "ecommerce_detected": False, "last_scanned": "2026-06-28T00:00:00+00:00"}


def test_ingest_dedupes_scores_and_respects_optout():
    engine = init_db("sqlite://")
    profile_registry.register(UtilityEnergyProfile())
    with Session(engine) as s:
        seed_taxonomy(s)
        s.add(OptOutRequest(kind="domain", value="optout.com", applied=True))
        s.commit()
        counts = ingest(s, FakeAdapter(), AdapterQuery(area={"city": "London"},
                        categories=["restaurant", "cafe"]),
                        scoring_profile_key="utility_energy", enrich_fn=_fake_enrich)
        assert counts["discovered"] == 3
        assert counts["skipped_duplicate"] == 1     # Joe Diner Dup
        assert counts["skipped_compliance"] == 1    # optout.com
        assert counts["stored"] == 1
        leads = s.exec(select(Lead)).all()
        assert len(leads) == 1
        lead = leads[0]
        assert lead.business_name == "Joe Diner"
        assert lead.score_total > 0
        assert lead.source_key == "fake_src"
        assert lead.source_license == "TESTLIC"
        assert lead.scoring_profile_key == "utility_energy"
        # source row + ingestion job recorded
        assert s.exec(select(LeadSource).where(LeadSource.key == "fake_src")).first()
        assert s.exec(select(IngestionJob)).first().status == "done"
