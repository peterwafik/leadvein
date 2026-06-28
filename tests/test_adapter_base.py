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
