from app.adapters.osm import OsmOverpassAdapter, build_overpass_ql
from app.adapters.base import AdapterQuery


SAMPLE_ELEMENT = {
    "type": "node", "id": 123, "lat": 51.5, "lon": -0.1,
    "tags": {"name": "Joe Diner", "amenity": "restaurant",
             "addr:housenumber": "12", "addr:street": "High St",
             "addr:city": "London", "addr:postcode": "SW1A 1AA",
             "phone": "+44 20 1234 5678", "website": "https://joediner.co.uk",
             "opening_hours": "Mo-Su 09:00-23:00"}}


class FakeResp:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p


class FakeSession:
    def __init__(self, payload): self.payload = payload; self.last = None
    def post(self, url, data=None, headers=None, timeout=None):
        self.last = data
        return FakeResp(self.payload)


def test_build_overpass_ql_includes_category_tag_and_area():
    ql = build_overpass_ql({"city": "London"}, ["restaurant"])
    assert "amenity" in ql and "restaurant" in ql
    assert "London" in ql


def test_discover_and_normalize():
    sess = FakeSession({"elements": [SAMPLE_ELEMENT]})
    a = OsmOverpassAdapter()
    raws = list(a.discover(AdapterQuery(area={"city": "London"},
                                        categories=["restaurant"]), session=sess))
    assert len(raws) == 1
    lead = a.normalize(raws[0])
    assert lead.business_name == "Joe Diner"
    assert "restaurant" in lead.category_keys
    assert lead.phone == "+44 20 1234 5678"
    assert lead.website_url == "https://joediner.co.uk"
    assert lead.address["city"] == "London"
    assert lead.address["postal_code"] == "SW1A 1AA"
    assert lead.source_key == "osm_overpass"
    assert "ODbL" in lead.source_license


def test_normalize_skips_unnamed():
    a = OsmOverpassAdapter()
    assert a.normalize({"tags": {"amenity": "restaurant"}}) is None
