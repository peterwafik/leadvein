from app.adapters.base import NormalizedLead
from app.enrich.website import enrich_website


def test_no_website_is_unreachable():
    lead = NormalizedLead(business_name="X", category_keys=[], address={})
    out = enrich_website(lead, fetch_fn=lambda u, **k: (None, None))
    assert out["website_reachable"] is False


def test_detects_online_ordering_and_ssl():
    lead = NormalizedLead(business_name="X", category_keys=[], address={},
                          website_url="https://x.com/")
    html = '<html><script src="https://fbgcdn.com/embedder/js/ewm2.js"></script></html>'
    out = enrich_website(lead, fetch_fn=lambda u, **k: ("https://x.com/", html))
    assert out["website_reachable"] is True
    assert out["ssl"] is True
    assert out["online_ordering_detected"] is True
