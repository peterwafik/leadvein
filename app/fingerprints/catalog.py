"""Custom recipe catalog — all vendor strings live here, NEVER in app/core.

Grep gate: test_fingerprint_grepclean.py asserts app/core/**/*.py is clean of
gloriafood | chownow | shopify | fbgcdn | ewm2 | data-glf | wappalyzer | urlscan | publicwww.

Two tiers:
  HIGH-CONFIDENCE  (enabled=True,  confidence="high"): dedicated-asset-domain tokens;
                   reliable discovery signal; safe to run in production.
  GREYED           (enabled=False, confidence="low"):  generic / self-hosted /
                   separate-domain tokens; seed but DO NOT use until tested.
"""
from __future__ import annotations

import json


def _j(v) -> str:
    """Serialise a Python object to a compact JSON string."""
    return json.dumps(v, separators=(",", ":"))


# ---------------------------------------------------------------------------
# HIGH-CONFIDENCE recipes  (enabled=True, confidence="high")
# ---------------------------------------------------------------------------
#
# gloriafood fields are VERBATIM from app/engine/recipes.py BUILTIN_RECIPES.
# All other high-confidence recipes use dedicated asset-domain tokens
# (a different CDN/asset host per vendor) that are not found on generic sites.

_HIGH: list[dict] = [
    # ------------------------------------------------------------------ Online Ordering / Restaurants
    {
        "recipe_key": "gloriafood",
        "category": "Online Ordering / Restaurants",
        "tech_type": "GloriaFood",
        "urlscan_query": "domain:fbgcdn.com",
        "publicwww_query": '"fbgcdn.com/embedder"',
        "verify_fingerprints_json": _j(["fbgcdn.com", "ewm2.js", "data-glf-cuid",
                                        "data-glf-ruid", "gloriafood"]),
        "id_extractors_json": _j({
            "ruid": r'data-glf-ruid=["\']([0-9a-fA-F-]+)["\']',
            "cuid": r'data-glf-cuid=["\']([0-9a-fA-F-]+)["\']',
        }),
        "exclude_hosts_json": _j(["gloriafood", "fbgcdn", "foodbooking"]),
    },
    {
        "recipe_key": "chownow",
        "category": "Online Ordering / Restaurants",
        "tech_type": "ChowNow",
        "urlscan_query": "domain:chownow.com",
        "publicwww_query": '"chownow.com"',
        "verify_fingerprints_json": _j(["chownow.com", "chownow"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["chownow"]),
    },
    # ------------------------------------------------------------------ E-commerce
    {
        "recipe_key": "shopify",
        "category": "E-commerce",
        "tech_type": "Shopify",
        "urlscan_query": "domain:cdn.shopify.com",
        "publicwww_query": '"cdn.shopify.com"',
        "verify_fingerprints_json": _j(["cdn.shopify.com", "shopify"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["shopify"]),
    },
    {
        "recipe_key": "bigcommerce",
        "category": "E-commerce",
        "tech_type": "BigCommerce",
        "urlscan_query": "domain:bigcommerce.com",
        "publicwww_query": '"bigcommerce.com"',
        "verify_fingerprints_json": _j(["bigcommerce.com", "bigcommerce"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["bigcommerce"]),
    },
    # ------------------------------------------------------------------ Website Builders
    {
        "recipe_key": "wix",
        "category": "Website Builders",
        "tech_type": "Wix",
        "urlscan_query": "domain:wixstatic.com",
        "publicwww_query": '"wixstatic.com"',
        "verify_fingerprints_json": _j(["wixstatic.com", "wix.com", "_wix"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["wix.com", "wixsite.com"]),
    },
    {
        "recipe_key": "squarespace",
        "category": "Website Builders",
        "tech_type": "Squarespace",
        "urlscan_query": "domain:static1.squarespace.com",
        "publicwww_query": '"static1.squarespace.com"',
        "verify_fingerprints_json": _j(["static1.squarespace.com", "squarespace"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["squarespace.com"]),
    },
    {
        "recipe_key": "webflow",
        "category": "Website Builders",
        "tech_type": "Webflow",
        "urlscan_query": "domain:cdn.prod.website-files.com",
        "publicwww_query": '"cdn.prod.website-files.com"',
        "verify_fingerprints_json": _j(["cdn.prod.website-files.com", "website-files.com", "webflow"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["webflow.com", "webflow.io"]),
    },
    {
        "recipe_key": "duda",
        "category": "Website Builders",
        "tech_type": "Duda",
        "urlscan_query": "domain:irp.cdn-website.com",
        "publicwww_query": '"irp.cdn-website.com"',
        "verify_fingerprints_json": _j(["irp.cdn-website.com", "cdn-website.com", "duda"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["duda.co", "dudamobile.com"]),
    },
    # ------------------------------------------------------------------ Booking / Scheduling
    {
        "recipe_key": "calendly",
        "category": "Booking / Scheduling",
        "tech_type": "Calendly",
        "urlscan_query": "domain:assets.calendly.com",
        "publicwww_query": '"assets.calendly.com"',
        "verify_fingerprints_json": _j(["assets.calendly.com", "calendly.com", "calendly"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["calendly.com"]),
    },
    # ------------------------------------------------------------------ Marketing / Chat widgets
    {
        "recipe_key": "intercom",
        "category": "Marketing / Chat widgets",
        "tech_type": "Intercom",
        "urlscan_query": "domain:widget.intercom.io",
        "publicwww_query": '"widget.intercom.io"',
        "verify_fingerprints_json": _j(["widget.intercom.io", "intercom"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["intercom.com", "intercom.io"]),
    },
    {
        "recipe_key": "zendesk",
        "category": "Marketing / Chat widgets",
        "tech_type": "Zendesk Chat",
        "urlscan_query": "domain:static.zdassets.com",
        "publicwww_query": '"static.zdassets.com"',
        "verify_fingerprints_json": _j(["static.zdassets.com", "zdassets", "zendesk"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["zendesk.com"]),
    },
    {
        "recipe_key": "tawkto",
        "category": "Marketing / Chat widgets",
        "tech_type": "Tawk.to",
        "urlscan_query": "domain:embed.tawk.to",
        "publicwww_query": '"embed.tawk.to"',
        "verify_fingerprints_json": _j(["embed.tawk.to", "tawk.to"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["tawk.to"]),
    },
    {
        "recipe_key": "crisp",
        "category": "Marketing / Chat widgets",
        "tech_type": "Crisp",
        "urlscan_query": "domain:client.crisp.chat",
        "publicwww_query": '"client.crisp.chat"',
        "verify_fingerprints_json": _j(["client.crisp.chat", "crisp.chat"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["crisp.chat"]),
    },
    {
        "recipe_key": "drift",
        "category": "Marketing / Chat widgets",
        "tech_type": "Drift",
        "urlscan_query": "domain:js.driftt.com",
        "publicwww_query": '"js.driftt.com"',
        "verify_fingerprints_json": _j(["js.driftt.com", "drift.com", "driftt"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["drift.com", "driftt.com"]),
    },
    {
        "recipe_key": "freshchat",
        "category": "Marketing / Chat widgets",
        "tech_type": "Freshchat",
        "urlscan_query": "domain:wchat.freshchat.com",
        "publicwww_query": '"wchat.freshchat.com"',
        "verify_fingerprints_json": _j(["wchat.freshchat.com", "freshchat"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["freshchat.com", "freshworks.com"]),
    },
    {
        "recipe_key": "livechat",
        "category": "Marketing / Chat widgets",
        "tech_type": "LiveChat",
        "urlscan_query": "domain:cdn.livechatinc.com",
        "publicwww_query": '"cdn.livechatinc.com"',
        "verify_fingerprints_json": _j(["cdn.livechatinc.com", "livechatinc", "livechat"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["livechat.com", "livechatinc.com"]),
    },
    # ------------------------------------------------------------------ Email / CRM Marketing
    {
        "recipe_key": "klaviyo",
        "category": "Email / CRM Marketing",
        "tech_type": "Klaviyo",
        "urlscan_query": "domain:static.klaviyo.com",
        "publicwww_query": '"static.klaviyo.com"',
        "verify_fingerprints_json": _j(["static.klaviyo.com", "klaviyo"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["klaviyo.com"]),
    },
    {
        "recipe_key": "hubspot",
        "category": "Email / CRM Marketing",
        "tech_type": "HubSpot",
        "urlscan_query": "domain:js.hs-scripts.com",
        "publicwww_query": '"js.hs-scripts.com"',
        "verify_fingerprints_json": _j(["js.hs-scripts.com", "hs-scripts", "hubspot"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["hubspot.com"]),
    },
    {
        "recipe_key": "marketo",
        "category": "Email / CRM Marketing",
        "tech_type": "Marketo",
        "urlscan_query": "domain:munchkin.marketo.net",
        "publicwww_query": '"munchkin.marketo.net"',
        "verify_fingerprints_json": _j(["munchkin.marketo.net", "marketo"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["marketo.com"]),
    },
    # ------------------------------------------------------------------ Analytics / Tag Managers
    {
        "recipe_key": "hotjar",
        "category": "Analytics / Tag Managers",
        "tech_type": "Hotjar",
        "urlscan_query": "domain:static.hotjar.com",
        "publicwww_query": '"static.hotjar.com"',
        "verify_fingerprints_json": _j(["static.hotjar.com", "hotjar"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["hotjar.com"]),
    },
    {
        "recipe_key": "segment",
        "category": "Analytics / Tag Managers",
        "tech_type": "Segment",
        "urlscan_query": "domain:cdn.segment.com",
        "publicwww_query": '"cdn.segment.com"',
        "verify_fingerprints_json": _j(["cdn.segment.com", "segment"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["segment.com"]),
    },
    # ------------------------------------------------------------------ Reviews / Social Proof
    {
        "recipe_key": "trustpilot",
        "category": "Reviews / Social Proof",
        "tech_type": "Trustpilot",
        "urlscan_query": "domain:widget.trustpilot.com",
        "publicwww_query": '"widget.trustpilot.com"',
        "verify_fingerprints_json": _j(["widget.trustpilot.com", "trustpilot"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["trustpilot.com"]),
    },
    {
        "recipe_key": "yotpo",
        "category": "Reviews / Social Proof",
        "tech_type": "Yotpo",
        "urlscan_query": "domain:staticw2.yotpo.com",
        "publicwww_query": '"yotpo.com"',
        "verify_fingerprints_json": _j(["staticw2.yotpo.com", "yotpo"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["yotpo.com"]),
    },
    # ------------------------------------------------------------------ Forms / Surveys
    {
        "recipe_key": "typeform",
        "category": "Forms / Surveys",
        "tech_type": "Typeform",
        "urlscan_query": "domain:embed.typeform.com",
        "publicwww_query": '"embed.typeform.com"',
        "verify_fingerprints_json": _j(["embed.typeform.com", "typeform"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["typeform.com"]),
    },
    {
        "recipe_key": "jotform",
        "category": "Forms / Surveys",
        "tech_type": "Jotform",
        "urlscan_query": "domain:form.jotform.com",
        "publicwww_query": '"jotform.com"',
        "verify_fingerprints_json": _j(["form.jotform.com", "jotform"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["jotform.com"]),
    },
    # ------------------------------------------------------------------ Payments
    {
        "recipe_key": "klarna",
        "category": "Payments",
        "tech_type": "Klarna",
        "urlscan_query": "domain:x.klarnacdn.net",
        "publicwww_query": '"klarnacdn.net"',
        "verify_fingerprints_json": _j(["x.klarnacdn.net", "klarna"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["klarna.com"]),
    },
]

# ---------------------------------------------------------------------------
# GREYED recipes  (enabled=False, confidence="low")
#
# Each entry below uses a generic, self-hosted, or separate-domain token.
# DO NOT enable in production without verifying the signal is sufficiently
# specific to your target segment (too many false-positives otherwise).
# ---------------------------------------------------------------------------

_GREYED: list[dict] = [
    # wordpress — self-hosted; wp-content path is ubiquitous across millions of
    # unrelated sites.  Token is not specific to any lead segment.  Test before use.
    {
        "recipe_key": "wordpress",
        "category": "Website Builders",
        "tech_type": "WordPress",
        "urlscan_query": '"wp-content"',
        "publicwww_query": '"wp-content/themes"',
        "verify_fingerprints_json": _j(["wp-content", "wp-includes", "wordpress"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["wordpress.com", "wordpress.org"]),
    },
    # woocommerce — self-hosted WooCommerce plugin; path is present on every WC store
    # but is too generic to distinguish leads.  Test before use.
    {
        "recipe_key": "woocommerce",
        "category": "E-commerce",
        "tech_type": "WooCommerce",
        "urlscan_query": '"woocommerce"',
        "publicwww_query": '"woocommerce"',
        "verify_fingerprints_json": _j(["woocommerce", "wp-content/plugins/woocommerce"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["woocommerce.com"]),
    },
    # magento — self-hosted; "Magento" meta-generator tag is common but the
    # platform is also found on vendor test/demo sites.  Test before use.
    {
        "recipe_key": "magento",
        "category": "E-commerce",
        "tech_type": "Magento",
        "urlscan_query": '"Magento"',
        "publicwww_query": '"Magento"',
        "verify_fingerprints_json": _j(["magento", "mage/"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["magento.com"]),
    },
    # prestashop — self-hosted; "/modules/ps_" path is reliable on PrestaShop
    # stores but the token also appears on dev/staging mirrors.  Test before use.
    {
        "recipe_key": "prestashop",
        "category": "E-commerce",
        "tech_type": "PrestaShop",
        "urlscan_query": '"prestashop"',
        "publicwww_query": '"PrestaShop"',
        "verify_fingerprints_json": _j(["prestashop", "/modules/ps_"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["prestashop.com"]),
    },
    # gravityforms — self-hosted WP plugin; "gform_" token is specific but only
    # present when a form is embedded on the page being scanned.  Test before use.
    {
        "recipe_key": "gravityforms",
        "category": "Forms / Surveys",
        "tech_type": "Gravity Forms",
        "urlscan_query": '"gravityforms"',
        "publicwww_query": '"gravityforms"',
        "verify_fingerprints_json": _j(["gravityforms", "gravity-forms", "gform_"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["gravityforms.com"]),
    },
    # google_analytics — separate-domain (google-analytics.com / googletagmanager.com);
    # present on ~50 % of all websites — not a useful lead signal.  Test before use.
    {
        "recipe_key": "google_analytics",
        "category": "Analytics / Tag Managers",
        "tech_type": "Google Analytics",
        "urlscan_query": '"google-analytics.com"',
        "publicwww_query": '"google-analytics.com/analytics.js"',
        "verify_fingerprints_json": _j(["google-analytics.com", "ga.js", "analytics.js"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["google.com", "google-analytics.com"]),
    },
    # meta_pixel — separate-domain (connect.facebook.net); ubiquitous on e-commerce
    # and SMB sites — not specific enough to be a useful lead signal.  Test before use.
    {
        "recipe_key": "meta_pixel",
        "category": "Analytics / Tag Managers",
        "tech_type": "Meta Pixel (Facebook)",
        "urlscan_query": '"connect.facebook.net/en_US/fbevents.js"',
        "publicwww_query": '"connect.facebook.net"',
        "verify_fingerprints_json": _j(["connect.facebook.net", "fbevents.js", "fbq("]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["facebook.com", "meta.com"]),
    },
    # google_ads — separate-domain (googleadservices.com); present on millions of
    # advertiser sites — far too generic to act as a lead signal.  Test before use.
    {
        "recipe_key": "google_ads",
        "category": "Analytics / Tag Managers",
        "tech_type": "Google Ads",
        "urlscan_query": '"googleadservices.com"',
        "publicwww_query": '"googleadservices.com/pagead/conversion.js"',
        "verify_fingerprints_json": _j(["googleadservices.com", "google_conversion", "gtag/js"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["google.com", "googleadservices.com"]),
    },
    # stripe — separate-domain (js.stripe.com); extremely common on any online
    # business — not specific enough to be a useful lead signal alone.  Test before use.
    {
        "recipe_key": "stripe",
        "category": "Payments",
        "tech_type": "Stripe",
        "urlscan_query": '"js.stripe.com"',
        "publicwww_query": '"js.stripe.com"',
        "verify_fingerprints_json": _j(["js.stripe.com", "stripe"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["stripe.com"]),
    },
    # paypal — separate-domain (paypal.com/sdk/js); highly generic and present on
    # millions of unrelated merchant sites.  Test before use.
    {
        "recipe_key": "paypal",
        "category": "Payments",
        "tech_type": "PayPal",
        "urlscan_query": '"paypal.com/sdk/js"',
        "publicwww_query": '"paypal.com/sdk/js"',
        "verify_fingerprints_json": _j(["paypal.com/sdk/js", "paypalobjects", "paypal-button"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["paypal.com"]),
    },
    # toast — toasttab.com domain is distinct but also appears on Toast's own
    # marketing site and partner pages.  Needs exclusion tuning before use.
    {
        "recipe_key": "toast",
        "category": "Online Ordering / Restaurants",
        "tech_type": "Toast",
        "urlscan_query": '"toasttab.com"',
        "publicwww_query": '"toasttab.com"',
        "verify_fingerprints_json": _j(["toasttab.com", "toast"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["toasttab.com", "toast.com"]),
    },
    # olo — separate-domain API; restaurants using Olo serve ordering via their
    # own subdomain, not oloapi.com directly.  Token requires custom verification.
    # Test before use.
    {
        "recipe_key": "olo",
        "category": "Online Ordering / Restaurants",
        "tech_type": "Olo",
        "urlscan_query": '"oloapi.com"',
        "publicwww_query": '"oloapi.com"',
        "verify_fingerprints_json": _j(["oloapi.com", "olo"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["olo.com", "oloapi.com"]),
    },
]

# ---------------------------------------------------------------------------
# Final catalog list — high-confidence first, then greyed.
# The library's seed_recipes() consumes this list.
# ---------------------------------------------------------------------------

_HIGH_DEFAULTS = {"confidence": "high", "enabled": True, "source": "custom"}
_GREY_DEFAULTS = {"confidence": "low",  "enabled": False, "source": "custom"}

CUSTOM_RECIPES: list[dict] = [
    {**_HIGH_DEFAULTS, **r} for r in _HIGH
] + [
    {**_GREY_DEFAULTS, **r} for r in _GREYED
]
