from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Recipe:
    id: str
    category: str
    type: str
    urlscan_query: str = ""
    publicwww_query: str = ""
    verify_fingerprints: list[str] = field(default_factory=list)
    id_extractors: dict[str, str] = field(default_factory=dict)
    exclude_hosts: list[str] = field(default_factory=list)
    logo: str = ""
    is_builtin: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def _r(**kw) -> Recipe:
    return Recipe(**kw)


BUILTIN_RECIPES: list[Recipe] = [
    # ---- Online Ordering / Restaurants ----
    _r(
        id="gloriafood",
        category="Online Ordering / Restaurants",
        type="GloriaFood",
        urlscan_query="domain:fbgcdn.com",
        publicwww_query='"fbgcdn.com/embedder"',
        verify_fingerprints=["fbgcdn.com", "ewm2.js", "data-glf-cuid",
                             "data-glf-ruid", "gloriafood"],
        id_extractors={
            "ruid": r'data-glf-ruid=["\']([0-9a-fA-F-]+)["\']',
            "cuid": r'data-glf-cuid=["\']([0-9a-fA-F-]+)["\']',
        },
        exclude_hosts=["gloriafood", "fbgcdn", "foodbooking"],
    ),
    _r(id="chownow", category="Online Ordering / Restaurants", type="ChowNow",
       urlscan_query="domain:chownow.com", publicwww_query='"chownow.com"',
       verify_fingerprints=["chownow.com", "chownow"], exclude_hosts=["chownow"]),
    _r(id="flipdish", category="Online Ordering / Restaurants", type="Flipdish",
       urlscan_query="domain:flipdish.com", publicwww_query='"flipdish.com"',
       verify_fingerprints=["flipdish.com", "flipdish"], exclude_hosts=["flipdish"]),

    # ---- E-commerce ----
    _r(id="shopify", category="E-commerce", type="Shopify",
       urlscan_query="domain:cdn.shopify.com", publicwww_query='"cdn.shopify.com"',
       verify_fingerprints=["cdn.shopify.com", "shopify"], exclude_hosts=["shopify"]),
    _r(id="woocommerce", category="E-commerce", type="WooCommerce",
       urlscan_query='"woocommerce"', publicwww_query='"woocommerce"',
       verify_fingerprints=["woocommerce", "wp-content/plugins/woocommerce"],
       exclude_hosts=["woocommerce.com"]),
    _r(id="bigcommerce", category="E-commerce", type="BigCommerce",
       urlscan_query="domain:bigcommerce.com", publicwww_query='"bigcommerce.com"',
       verify_fingerprints=["bigcommerce.com", "bigcommerce"], exclude_hosts=["bigcommerce"]),
    _r(id="magento", category="E-commerce", type="Magento",
       urlscan_query='"Magento"', publicwww_query='"Magento"',
       verify_fingerprints=["magento", "mage/"], exclude_hosts=["magento.com"]),

    # ---- Website Builders ----
    _r(id="wix", category="Website Builders", type="Wix",
       urlscan_query="domain:wixstatic.com", publicwww_query='"wixstatic.com"',
       verify_fingerprints=["wixstatic.com", "wix.com", "_wix"], exclude_hosts=["wix.com", "wixsite.com"]),
    _r(id="squarespace", category="Website Builders", type="Squarespace",
       urlscan_query="domain:squarespace.com", publicwww_query='"squarespace.com"',
       verify_fingerprints=["squarespace.com", "static1.squarespace"], exclude_hosts=["squarespace.com"]),
    _r(id="webflow", category="Website Builders", type="Webflow",
       urlscan_query="domain:webflow.com", publicwww_query='"webflow.com"',
       verify_fingerprints=["webflow.com", "wf-", "webflow"], exclude_hosts=["webflow.com", "webflow.io"]),
    _r(id="godaddy", category="Website Builders", type="GoDaddy Websites",
       urlscan_query="domain:img1.wsimg.com", publicwww_query='"img1.wsimg.com"',
       verify_fingerprints=["img1.wsimg.com", "wsimg.com"], exclude_hosts=["godaddy.com", "wsimg.com"]),

    # ---- Booking / Scheduling ----
    _r(id="calendly", category="Booking / Scheduling", type="Calendly",
       urlscan_query="domain:assets.calendly.com", publicwww_query='"assets.calendly.com"',
       verify_fingerprints=["assets.calendly.com", "calendly.com", "calendly"], exclude_hosts=["calendly.com"]),
    _r(id="acuity", category="Booking / Scheduling", type="Acuity",
       urlscan_query="domain:acuityscheduling.com", publicwww_query='"acuityscheduling.com"',
       verify_fingerprints=["acuityscheduling.com", "acuity"], exclude_hosts=["acuityscheduling.com"]),
    _r(id="calcom", category="Booking / Scheduling", type="Cal.com",
       urlscan_query="domain:cal.com", publicwww_query='"cal.com/embed"',
       verify_fingerprints=["cal.com/embed", "cal-embed", "app.cal.com"], exclude_hosts=["cal.com"]),
    _r(id="mindbody", category="Booking / Scheduling", type="Mindbody",
       urlscan_query="domain:mindbodyonline.com", publicwww_query='"mindbodyonline.com"',
       verify_fingerprints=["mindbodyonline.com", "mindbody"], exclude_hosts=["mindbodyonline.com"]),

    # ---- Marketing / Chat widgets ----
    _r(id="hubspot", category="Marketing / Chat widgets", type="HubSpot",
       urlscan_query="domain:js.hs-scripts.com", publicwww_query='"js.hs-scripts.com"',
       verify_fingerprints=["js.hs-scripts.com", "hs-scripts", "hubspot"], exclude_hosts=["hubspot.com"]),
    _r(id="intercom", category="Marketing / Chat widgets", type="Intercom",
       urlscan_query="domain:widget.intercom.io", publicwww_query='"widget.intercom.io"',
       verify_fingerprints=["widget.intercom.io", "intercom"], exclude_hosts=["intercom.com", "intercom.io"]),
    _r(id="drift", category="Marketing / Chat widgets", type="Drift",
       urlscan_query="domain:js.driftt.com", publicwww_query='"js.driftt.com"',
       verify_fingerprints=["js.driftt.com", "drift.com", "driftt"], exclude_hosts=["drift.com", "driftt.com"]),
    _r(id="tawkto", category="Marketing / Chat widgets", type="Tawk.to",
       urlscan_query="domain:embed.tawk.to", publicwww_query='"embed.tawk.to"',
       verify_fingerprints=["embed.tawk.to", "tawk.to"], exclude_hosts=["tawk.to"]),

    # ---- Payments ----
    _r(id="stripe_checkout", category="Payments", type="Stripe Checkout",
       urlscan_query="domain:js.stripe.com", publicwww_query='"js.stripe.com"',
       verify_fingerprints=["js.stripe.com", "stripe"], exclude_hosts=["stripe.com"]),
    _r(id="paypal_buttons", category="Payments", type="PayPal Buttons",
       urlscan_query="domain:paypal.com", publicwww_query='"paypal.com/sdk/js"',
       verify_fingerprints=["paypal.com/sdk/js", "paypalobjects", "paypal-button"],
       exclude_hosts=["paypal.com"]),
]


def get_builtin(recipe_id: str) -> Recipe | None:
    for r in BUILTIN_RECIPES:
        if r.id == recipe_id:
            return r
    return None


def recipes_by_category(recipes: list[Recipe]) -> dict[str, list[Recipe]]:
    grouped: dict[str, list[Recipe]] = {}
    for r in recipes:
        grouped.setdefault(r.category, []).append(r)
    return grouped
