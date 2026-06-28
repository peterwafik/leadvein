from __future__ import annotations

from datetime import datetime, timezone

from app.adapters.base import NormalizedLead
from app.engine.enrich import fetch

# intent signal -> substrings that indicate it in page source
INTENT_FINGERPRINTS = {
    "online_ordering_detected": ["fbgcdn.com", "ewm2.js", "gloriafood", "chownow",
                                 "flipdish", "toasttab", "slicelife"],
    "booking_detected": ["calendly.com", "acuityscheduling", "simplybook",
                         "setmore", "mindbodyonline"],
    "payment_provider_detected": ["js.stripe.com", "paypal.com/sdk", "squareup",
                                  "klarna", "adyen", "gocardless"],
    "ecommerce_detected": ["cdn.shopify.com", "woocommerce", "bigcommerce",
                           "magento", "ecwid"],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def enrich_website(lead: NormalizedLead, *, fetch_fn=fetch) -> dict:
    out = {"website_reachable": False, "ssl": False, "online_ordering_detected": False,
           "booking_detected": False, "payment_provider_detected": False,
           "ecommerce_detected": False, "last_scanned": _now()}
    if not lead.website_url:
        return out
    final_url, html = fetch_fn(lead.website_url)
    if not html:
        return out
    out["website_reachable"] = True
    out["ssl"] = (final_url or lead.website_url).startswith("https://")
    low = html.lower()
    for signal, tokens in INTENT_FINGERPRINTS.items():
        out[signal] = any(tok in low for tok in tokens)
    return out
