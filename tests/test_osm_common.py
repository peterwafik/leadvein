from __future__ import annotations

from app.adapters.osm_common import normalized_from_tags


def _tags(**kw):
    base = {"name": "Common Cafe", "amenity": "cafe", "addr:city": "Oxford",
            "addr:street": "High St", "addr:housenumber": "12",
            "addr:postcode": "OX1 1AA", "addr:country": "GB",
            "contact:phone": "+44 1865 000000", "website": "https://commoncafe.example",
            "opening_hours": "Mo-Su 08:00-18:00"}
    base.update(kw)
    return base


def test_full_mapping():
    n = normalized_from_tags(_tags(), lat=51.75, lon=-1.25, raw_ref="node/1",
                             categories=["cafe"], source_key="osm_geofabrik")
    assert n.business_name == "Common Cafe"
    assert n.address == {"line1": "12 High St", "city": "Oxford", "region": "",
                         "postal_code": "OX1 1AA", "country": "GB",
                         "lat": 51.75, "lon": -1.25}
    assert n.phone == "+44 1865 000000"
    assert n.website_url == "https://commoncafe.example"
    assert n.attributes.get("open_7_days") is True
    assert n.raw_ref == "node/1"


def test_nameless_skipped():
    assert normalized_from_tags(_tags(name=""), lat=0, lon=0, raw_ref="node/2",
                                categories=["cafe"], source_key="x") is None


def test_contact_prefixed_fallbacks():
    t = _tags()
    del t["website"]
    t["contact:website"] = "https://alt.example"
    t["email"] = "hi@commoncafe.example"
    n = normalized_from_tags(t, lat=0, lon=0, raw_ref="way/3",
                             categories=["cafe"], source_key="x")
    assert n.website_url == "https://alt.example"
    assert n.public_email == "hi@commoncafe.example"
