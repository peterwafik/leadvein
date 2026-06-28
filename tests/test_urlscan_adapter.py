from app.adapters.urlscan_fingerprint import UrlscanFingerprintAdapter
from app.adapters.base import AdapterQuery

HTML = ('<html><title>Marios</title><body>'
        '<script src="https://fbgcdn.com/embedder/js/ewm2.js"></script>'
        '<a href="mailto:info@marios.com">e</a></body></html>')


def test_discover_uses_supplied_hosts_and_normalize_detects_tech():
    a = UrlscanFingerprintAdapter()
    q = AdapterQuery(area={}, categories=[],
                     extra={"recipe_id": "gloriafood", "hosts": ["marios.com"]})
    raws = list(a.discover(q))
    assert raws == [{"host": "marios.com", "recipe_id": "gloriafood"}]

    def fake_fetch(url, **kw):
        return url, HTML
    lead = a.normalize(raws[0], fetch_fn=fake_fetch)
    assert lead.business_name == "Marios"
    assert lead.website_url.startswith("https://marios.com")
    assert lead.attributes.get("on_platform") is True
    assert lead.source_key == "urlscan_fingerprint"
