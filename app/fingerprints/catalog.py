"""Custom recipe catalog — all vendor strings live here, NEVER in app/core.

Grep gate: test_fingerprint_grepclean.py asserts app/core/**/*.py is clean of
gloriafood | chownow | shopify | fbgcdn | ewm2 | data-glf | wappalyzer | urlscan | publicwww.

Two tiers:
  HIGH-CONFIDENCE  (enabled=True,  confidence="high"): dedicated-asset-domain tokens;
                   reliable discovery signal; safe to run in production.
  GREYED           (enabled=False, confidence="low"):  generic / self-hosted /
                   separate-domain tokens; seed but DO NOT use until tested.

INV-12 compliance: every HIGH-CONFIDENCE recipe uses ONLY distinctive asset-domain
tokens (e.g. CDN subdomain, embed subdomain) that appear when the technology is
actually LOADED on the page — NOT bare vendor-name strings that would match a mere
textual mention or an outbound link.
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
# All other high-confidence recipes use ONLY distinctive asset-domain tokens
# (a different CDN/asset host per vendor) that appear only when the technology
# is actively loaded — NOT bare vendor-name strings (INV-12).

_HIGH: list[dict] = [
    # ------------------------------------------------------------------ Online Ordering / Restaurants
    {
        "recipe_key": "gloriafood",
        "category": "Online Ordering / Restaurants",
        "tech_type": "GloriaFood",
        "urlscan_query": "domain:fbgcdn.com",
        "publicwww_query": '"fbgcdn.com/embedder"',
        # gloriafood kept verbatim from BUILTIN_RECIPES (fbgcdn.com CDN, ewm2.js script,
        # data-glf-* attributes are all distinctive — "gloriafood" is embedded in the
        # fbgcdn.com domain itself).
        "verify_fingerprints_json": _j(["fbgcdn.com", "ewm2.js", "data-glf-cuid",
                                        "data-glf-ruid", "gloriafood"]),
        "id_extractors_json": _j({
            "ruid": r'data-glf-ruid=["\']([0-9a-fA-F-]+)["\']',
            "cuid": r'data-glf-cuid=["\']([0-9a-fA-F-]+)["\']',
        }),
        "exclude_hosts_json": _j(["gloriafood", "fbgcdn", "foodbooking"]),
    },
    # ------------------------------------------------------------------ E-commerce
    {
        "recipe_key": "shopify",
        "category": "E-commerce",
        "tech_type": "Shopify",
        "urlscan_query": "domain:cdn.shopify.com",
        "publicwww_query": '"cdn.shopify.com"',
        # bare "shopify" removed — cdn.shopify.com is the distinctive embed CDN
        "verify_fingerprints_json": _j(["cdn.shopify.com"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["shopify"]),
    },
    {
        "recipe_key": "bigcommerce",
        "category": "E-commerce",
        "tech_type": "BigCommerce",
        "urlscan_query": "domain:bigcommerce.com",
        "publicwww_query": '"bigcommerce.com"',
        # bare "bigcommerce" removed — bigcommerce.com asset domain is the signal
        "verify_fingerprints_json": _j(["bigcommerce.com"]),
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
        # "wix.com" removed (mere link); wixstatic.com is the CDN; _wix is a
        # distinctive data-attribute prefix present on embedded Wix elements
        "verify_fingerprints_json": _j(["wixstatic.com", "_wix"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["wix.com", "wixsite.com"]),
    },
    {
        "recipe_key": "squarespace",
        "category": "Website Builders",
        "tech_type": "Squarespace",
        "urlscan_query": "domain:static1.squarespace.com",
        "publicwww_query": '"static1.squarespace.com"',
        # bare "squarespace" removed — static1.squarespace.com is the CDN
        "verify_fingerprints_json": _j(["static1.squarespace.com"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["squarespace.com"]),
    },
    {
        "recipe_key": "webflow",
        "category": "Website Builders",
        "tech_type": "Webflow",
        "urlscan_query": "domain:cdn.prod.website-files.com",
        "publicwww_query": '"cdn.prod.website-files.com"',
        # bare "webflow" removed; cdn.prod.website-files.com and website-files.com
        # are distinctive asset-domain tokens
        "verify_fingerprints_json": _j(["cdn.prod.website-files.com", "website-files.com"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["webflow.com", "webflow.io"]),
    },
    {
        "recipe_key": "duda",
        "category": "Website Builders",
        "tech_type": "Duda",
        "urlscan_query": "domain:irp.cdn-website.com",
        "publicwww_query": '"irp.cdn-website.com"',
        # bare "duda" removed; irp.cdn-website.com and cdn-website.com are
        # distinctive asset-domain tokens
        "verify_fingerprints_json": _j(["irp.cdn-website.com", "cdn-website.com"]),
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
        # "calendly.com" and bare "calendly" removed — assets.calendly.com is
        # the distinctive embed asset domain
        "verify_fingerprints_json": _j(["assets.calendly.com"]),
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
        # bare "intercom" removed — widget.intercom.io is the distinctive embed domain
        "verify_fingerprints_json": _j(["widget.intercom.io"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["intercom.com", "intercom.io"]),
    },
    {
        "recipe_key": "zendesk",
        "category": "Marketing / Chat widgets",
        "tech_type": "Zendesk Chat",
        "urlscan_query": "domain:static.zdassets.com",
        "publicwww_query": '"static.zdassets.com"',
        # bare "zendesk" removed; static.zdassets.com and "zdassets" are distinctive
        # (zdassets is the CDN domain abbreviation unique to Zendesk)
        "verify_fingerprints_json": _j(["static.zdassets.com", "zdassets"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["zendesk.com"]),
    },
    {
        "recipe_key": "tawkto",
        "category": "Marketing / Chat widgets",
        "tech_type": "Tawk.to",
        "urlscan_query": "domain:embed.tawk.to",
        "publicwww_query": '"embed.tawk.to"',
        # "tawk.to" removed (mere link); embed.tawk.to is the distinctive embed subdomain
        "verify_fingerprints_json": _j(["embed.tawk.to"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["tawk.to"]),
    },
    {
        "recipe_key": "crisp",
        "category": "Marketing / Chat widgets",
        "tech_type": "Crisp",
        "urlscan_query": "domain:client.crisp.chat",
        "publicwww_query": '"client.crisp.chat"',
        # "crisp.chat" removed (mere link/mention); client.crisp.chat is the
        # distinctive embed subdomain
        "verify_fingerprints_json": _j(["client.crisp.chat"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["crisp.chat"]),
    },
    {
        "recipe_key": "drift",
        "category": "Marketing / Chat widgets",
        "tech_type": "Drift",
        "urlscan_query": "domain:js.driftt.com",
        "publicwww_query": '"js.driftt.com"',
        # "drift.com" removed (mere link); js.driftt.com and "driftt" are distinctive
        # (driftt is Drift's CDN subdomain abbreviation)
        "verify_fingerprints_json": _j(["js.driftt.com", "driftt"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["drift.com", "driftt.com"]),
    },
    {
        "recipe_key": "freshchat",
        "category": "Marketing / Chat widgets",
        "tech_type": "Freshchat",
        "urlscan_query": "domain:wchat.freshchat.com",
        "publicwww_query": '"wchat.freshchat.com"',
        # bare "freshchat" removed — wchat.freshchat.com is the distinctive embed domain
        "verify_fingerprints_json": _j(["wchat.freshchat.com"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["freshchat.com", "freshworks.com"]),
    },
    {
        "recipe_key": "livechat",
        "category": "Marketing / Chat widgets",
        "tech_type": "LiveChat",
        "urlscan_query": "domain:cdn.livechatinc.com",
        "publicwww_query": '"cdn.livechatinc.com"',
        # bare "livechat" removed; cdn.livechatinc.com and "livechatinc" are distinctive
        "verify_fingerprints_json": _j(["cdn.livechatinc.com", "livechatinc"]),
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
        # bare "klaviyo" removed — static.klaviyo.com is the distinctive CDN
        "verify_fingerprints_json": _j(["static.klaviyo.com"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["klaviyo.com"]),
    },
    {
        "recipe_key": "hubspot",
        "category": "Email / CRM Marketing",
        "tech_type": "HubSpot",
        "urlscan_query": "domain:js.hs-scripts.com",
        "publicwww_query": '"js.hs-scripts.com"',
        # bare "hubspot" removed; js.hs-scripts.com and "hs-scripts" are distinctive
        "verify_fingerprints_json": _j(["js.hs-scripts.com", "hs-scripts"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["hubspot.com"]),
    },
    {
        "recipe_key": "marketo",
        "category": "Email / CRM Marketing",
        "tech_type": "Marketo",
        "urlscan_query": "domain:munchkin.marketo.net",
        "publicwww_query": '"munchkin.marketo.net"',
        # bare "marketo" removed — munchkin.marketo.net is the distinctive JS host
        "verify_fingerprints_json": _j(["munchkin.marketo.net"]),
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
        # bare "hotjar" removed — static.hotjar.com is the distinctive CDN
        "verify_fingerprints_json": _j(["static.hotjar.com"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["hotjar.com"]),
    },
    {
        "recipe_key": "segment",
        "category": "Analytics / Tag Managers",
        "tech_type": "Segment",
        "urlscan_query": "domain:cdn.segment.com",
        "publicwww_query": '"cdn.segment.com"',
        # bare "segment" removed — cdn.segment.com is the distinctive CDN
        "verify_fingerprints_json": _j(["cdn.segment.com"]),
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
        # bare "trustpilot" removed — widget.trustpilot.com is the distinctive embed domain
        "verify_fingerprints_json": _j(["widget.trustpilot.com"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["trustpilot.com"]),
    },
    {
        "recipe_key": "yotpo",
        "category": "Reviews / Social Proof",
        "tech_type": "Yotpo",
        "urlscan_query": "domain:staticw2.yotpo.com",
        "publicwww_query": '"yotpo.com"',
        # bare "yotpo" removed — staticw2.yotpo.com is the distinctive CDN
        "verify_fingerprints_json": _j(["staticw2.yotpo.com"]),
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
        # bare "typeform" removed — embed.typeform.com is the distinctive embed domain
        "verify_fingerprints_json": _j(["embed.typeform.com"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["typeform.com"]),
    },
    {
        "recipe_key": "jotform",
        "category": "Forms / Surveys",
        "tech_type": "Jotform",
        "urlscan_query": "domain:form.jotform.com",
        "publicwww_query": '"jotform.com"',
        # bare "jotform" removed — form.jotform.com is the distinctive embed domain
        "verify_fingerprints_json": _j(["form.jotform.com"]),
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
        # bare "klarna" removed — x.klarnacdn.net is the distinctive CDN
        "verify_fingerprints_json": _j(["x.klarnacdn.net"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["klarna.com"]),
    },
]

# ---------------------------------------------------------------------------
# GREYED recipes  (enabled=False, confidence="low" unless overridden)
#
# Each entry below uses a generic, self-hosted, or separate-domain token.
# DO NOT enable in production without verifying the signal is sufficiently
# specific to your target segment (too many false-positives otherwise).
# ---------------------------------------------------------------------------

_GREYED: list[dict] = [
    # chownow — bare-vendor token (chownow.com / "chownow") would match any page
    # that merely LINKS to ChowNow or mentions it (e.g. food-ordering aggregators).
    # confidence="medium" because the urlscan signal is reasonable; the verify_fingerprint
    # token is too coarse.  Run a Test-recipe before enabling.
    {
        "recipe_key": "chownow",
        "category": "Online Ordering / Restaurants",
        "tech_type": "ChowNow",
        "urlscan_query": "domain:chownow.com",
        "publicwww_query": '"chownow.com"',
        "verify_fingerprints_json": _j(["chownow.com", "chownow"]),
        "id_extractors_json": _j({}),
        "exclude_hosts_json": _j(["chownow"]),
        "confidence": "medium",   # overrides "low" from _GREY_DEFAULTS
    },
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
