from app.adapters.base import SourceMeta, AdapterQuery, NormalizedLead, LeadSourceAdapter
from app.adapters import registry


class FakeAdapter:
    meta = SourceMeta(key="fake", name="Fake", type="test", url="http://x",
                      license="TEST")

    def discover(self, query):
        return [{"name": "Joe Diner", "cat": "restaurant"},
                {"name": "No Name", "cat": "cafe"}]

    def normalize(self, raw):
        if not raw.get("name"):
            return None
        return NormalizedLead(business_name=raw["name"], category_keys=[raw["cat"]],
                              address={"city": "London"}, source_key=self.meta.key,
                              source_license=self.meta.license, raw_ref=raw["name"])

    def attribution(self):
        return "Fake attribution"


def test_adapter_protocol_and_registry():
    a = FakeAdapter()
    assert isinstance(a, LeadSourceAdapter)  # structural/Protocol check
    registry.register(a)
    assert "fake" in registry.all_keys()
    got = registry.get("fake")
    raws = list(got.discover(AdapterQuery(area={}, categories=["restaurant"])))
    leads = [got.normalize(r) for r in raws]
    assert leads[0].business_name == "Joe Diner"
    assert leads[0].category_keys == ["restaurant"]
    assert leads[0].source_license == "TEST"


def test_register_providers_appears_in_list_status_disabled(monkeypatch):
    """register_providers() adds companies_house + hunter; both disabled without env keys."""
    from app.adapters.providers import register_providers

    # Ensure provider env keys are absent so both adapters report enabled=False
    monkeypatch.delenv("LEADVAULT_COMPANIES_HOUSE_KEY", raising=False)
    monkeypatch.delenv("LEADVAULT_HUNTER_KEY", raising=False)

    register_providers()

    statuses = {s["key"]: s for s in registry.list_status()}
    assert "companies_house" in statuses, "companies_house not found in registry"
    assert "hunter" in statuses, "hunter not found in registry"
    assert statuses["companies_house"]["enabled"] is False
    assert statuses["hunter"]["enabled"] is False
