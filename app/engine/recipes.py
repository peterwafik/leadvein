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

    # ---- Online Ordering / Restaurants (more) ----
    _r(id="toast", category="Online Ordering / Restaurants", type="Toast",
       urlscan_query="domain:toasttab.com", publicwww_query='"toasttab.com"',
       verify_fingerprints=["toasttab.com", "toast"], exclude_hosts=["toasttab.com", "toast.com"]),
    _r(id="bentobox", category="Online Ordering / Restaurants", type="BentoBox",
       urlscan_query="domain:getbento.com", publicwww_query='"getbento.com"',
       verify_fingerprints=["getbento.com", "bentobox"], exclude_hosts=["getbento.com"]),
    _r(id="slice", category="Online Ordering / Restaurants", type="Slice",
       urlscan_query="domain:slicelife.com", publicwww_query='"slicelife.com"',
       verify_fingerprints=["slicelife.com", "slice"], exclude_hosts=["slicelife.com"]),

    # ---- E-commerce (more) ----
    _r(id="ecwid", category="E-commerce", type="Ecwid",
       urlscan_query="domain:app.ecwid.com", publicwww_query='"app.ecwid.com"',
       verify_fingerprints=["app.ecwid.com", "ecwid"], exclude_hosts=["ecwid.com"]),
    _r(id="prestashop", category="E-commerce", type="PrestaShop",
       urlscan_query='"prestashop"', publicwww_query='"PrestaShop"',
       verify_fingerprints=["prestashop", "/modules/ps_"], exclude_hosts=["prestashop.com"]),
    _r(id="volusion", category="E-commerce", type="Volusion",
       urlscan_query="domain:volusion.com", publicwww_query='"volusion.com"',
       verify_fingerprints=["volusion.com", "volusion"], exclude_hosts=["volusion.com"]),

    # ---- Website Builders (more) ----
    _r(id="weebly", category="Website Builders", type="Weebly",
       urlscan_query="domain:editmysite.com", publicwww_query='"editmysite.com"',
       verify_fingerprints=["editmysite.com", "weebly"], exclude_hosts=["weebly.com", "weeblysite.com"]),
    _r(id="duda", category="Website Builders", type="Duda",
       urlscan_query="domain:dudamobile.com", publicwww_query='"dudamobile.com"',
       verify_fingerprints=["dudamobile.com", "_duda_", "duda"], exclude_hosts=["duda.co", "dudamobile.com"]),
    _r(id="jimdo", category="Website Builders", type="Jimdo",
       urlscan_query="domain:jimdo.com", publicwww_query='"jimdo.com"',
       verify_fingerprints=["jimdo.com", "jimdo"], exclude_hosts=["jimdo.com", "jimdofree.com"]),

    # ---- Booking / Scheduling (more) ----
    _r(id="setmore", category="Booking / Scheduling", type="Setmore",
       urlscan_query="domain:setmore.com", publicwww_query='"setmore.com"',
       verify_fingerprints=["setmore.com", "setmore"], exclude_hosts=["setmore.com"]),
    _r(id="simplybook", category="Booking / Scheduling", type="SimplyBook.me",
       urlscan_query="domain:simplybook.me", publicwww_query='"simplybook.me"',
       verify_fingerprints=["simplybook.me", "simplybook"], exclude_hosts=["simplybook.me"]),
    _r(id="housecallpro", category="Booking / Scheduling", type="Housecall Pro",
       urlscan_query="domain:housecallpro.com", publicwww_query='"housecallpro.com"',
       verify_fingerprints=["housecallpro.com", "housecall"], exclude_hosts=["housecallpro.com"]),

    # ---- Marketing / Chat widgets (more) ----
    _r(id="zendesk", category="Marketing / Chat widgets", type="Zendesk Chat",
       urlscan_query="domain:static.zdassets.com", publicwww_query='"static.zdassets.com"',
       verify_fingerprints=["static.zdassets.com", "zdassets", "zendesk"], exclude_hosts=["zendesk.com"]),
    _r(id="livechat", category="Marketing / Chat widgets", type="LiveChat",
       urlscan_query="domain:cdn.livechatinc.com", publicwww_query='"cdn.livechatinc.com"',
       verify_fingerprints=["cdn.livechatinc.com", "livechatinc", "livechat"], exclude_hosts=["livechat.com", "livechatinc.com"]),
    _r(id="crisp", category="Marketing / Chat widgets", type="Crisp",
       urlscan_query="domain:client.crisp.chat", publicwww_query='"client.crisp.chat"',
       verify_fingerprints=["client.crisp.chat", "crisp.chat"], exclude_hosts=["crisp.chat"]),
    _r(id="freshchat", category="Marketing / Chat widgets", type="Freshchat",
       urlscan_query="domain:wchat.freshchat.com", publicwww_query='"wchat.freshchat.com"',
       verify_fingerprints=["wchat.freshchat.com", "freshchat"], exclude_hosts=["freshchat.com", "freshworks.com"]),
    _r(id="olark", category="Marketing / Chat widgets", type="Olark",
       urlscan_query="domain:static.olark.com", publicwww_query='"static.olark.com"',
       verify_fingerprints=["static.olark.com", "olark"], exclude_hosts=["olark.com"]),

    # ---- Analytics / Tag Managers (NEW) ----
    _r(id="gtm", category="Analytics / Tag Managers", type="Google Tag Manager",
       urlscan_query="domain:googletagmanager.com", publicwww_query='"googletagmanager.com"',
       verify_fingerprints=["googletagmanager.com", "gtm.js", "gtag/js"], exclude_hosts=["google.com", "googletagmanager.com"]),
    _r(id="hotjar", category="Analytics / Tag Managers", type="Hotjar",
       urlscan_query="domain:static.hotjar.com", publicwww_query='"static.hotjar.com"',
       verify_fingerprints=["static.hotjar.com", "hotjar"], exclude_hosts=["hotjar.com"]),
    _r(id="segment", category="Analytics / Tag Managers", type="Segment",
       urlscan_query="domain:cdn.segment.com", publicwww_query='"cdn.segment.com"',
       verify_fingerprints=["cdn.segment.com", "segment"], exclude_hosts=["segment.com"]),
    _r(id="mixpanel", category="Analytics / Tag Managers", type="Mixpanel",
       urlscan_query="domain:cdn.mxpnl.com", publicwww_query='"cdn.mxpnl.com"',
       verify_fingerprints=["cdn.mxpnl.com", "mixpanel"], exclude_hosts=["mixpanel.com"]),
    _r(id="plausible", category="Analytics / Tag Managers", type="Plausible",
       urlscan_query="domain:plausible.io", publicwww_query='"plausible.io"',
       verify_fingerprints=["plausible.io", "plausible"], exclude_hosts=["plausible.io"]),

    # ---- Email / CRM Marketing (NEW) ----
    _r(id="mailchimp", category="Email / CRM Marketing", type="Mailchimp",
       urlscan_query="domain:chimpstatic.com", publicwww_query='"chimpstatic.com"',
       verify_fingerprints=["chimpstatic.com", "list-manage.com", "mailchimp"], exclude_hosts=["mailchimp.com"]),
    _r(id="klaviyo", category="Email / CRM Marketing", type="Klaviyo",
       urlscan_query="domain:static.klaviyo.com", publicwww_query='"static.klaviyo.com"',
       verify_fingerprints=["static.klaviyo.com", "klaviyo"], exclude_hosts=["klaviyo.com"]),
    _r(id="activecampaign", category="Email / CRM Marketing", type="ActiveCampaign",
       urlscan_query="domain:activehosted.com", publicwww_query='"activehosted.com"',
       verify_fingerprints=["activehosted.com", "activecampaign"], exclude_hosts=["activecampaign.com"]),
    _r(id="convertkit", category="Email / CRM Marketing", type="ConvertKit / Kit",
       urlscan_query="domain:convertkit.com", publicwww_query='"ck.page"',
       verify_fingerprints=["convertkit.com", "ck.page", "convertkit"], exclude_hosts=["convertkit.com", "kit.com"]),
    _r(id="marketo", category="Email / CRM Marketing", type="Marketo",
       urlscan_query="domain:munchkin.marketo.net", publicwww_query='"munchkin.marketo.net"',
       verify_fingerprints=["munchkin.marketo.net", "marketo"], exclude_hosts=["marketo.com"]),

    # ---- Reviews / Social Proof (NEW) ----
    _r(id="trustpilot", category="Reviews / Social Proof", type="Trustpilot",
       urlscan_query="domain:widget.trustpilot.com", publicwww_query='"widget.trustpilot.com"',
       verify_fingerprints=["widget.trustpilot.com", "trustpilot"], exclude_hosts=["trustpilot.com"]),
    _r(id="yotpo", category="Reviews / Social Proof", type="Yotpo",
       urlscan_query="domain:staticw2.yotpo.com", publicwww_query='"yotpo.com"',
       verify_fingerprints=["staticw2.yotpo.com", "yotpo"], exclude_hosts=["yotpo.com"]),
    _r(id="judgeme", category="Reviews / Social Proof", type="Judge.me",
       urlscan_query="domain:judge.me", publicwww_query='"judge.me"',
       verify_fingerprints=["judge.me", "judgeme"], exclude_hosts=["judge.me"]),

    # ---- Forms / Surveys (NEW) ----
    _r(id="typeform", category="Forms / Surveys", type="Typeform",
       urlscan_query="domain:embed.typeform.com", publicwww_query='"embed.typeform.com"',
       verify_fingerprints=["embed.typeform.com", "typeform"], exclude_hosts=["typeform.com"]),
    _r(id="jotform", category="Forms / Surveys", type="Jotform",
       urlscan_query="domain:form.jotform.com", publicwww_query='"jotform.com"',
       verify_fingerprints=["form.jotform.com", "jotform"], exclude_hosts=["jotform.com"]),
    _r(id="gravityforms", category="Forms / Surveys", type="Gravity Forms",
       urlscan_query='"gravityforms"', publicwww_query='"gravityforms"',
       verify_fingerprints=["gravityforms", "gravity-forms", "gform_"], exclude_hosts=["gravityforms.com"]),

    # ---- Payments (more) ----
    _r(id="square", category="Payments", type="Square",
       urlscan_query="domain:squareup.com", publicwww_query='"web.squarecdn.com"',
       verify_fingerprints=["squareup.com", "squarecdn.com", "web.squarecdn.com"], exclude_hosts=["squareup.com", "square.com"]),
    _r(id="klarna", category="Payments", type="Klarna",
       urlscan_query="domain:x.klarnacdn.net", publicwww_query='"klarnacdn.net"',
       verify_fingerprints=["x.klarnacdn.net", "klarna"], exclude_hosts=["klarna.com"]),
    _r(id="adyen", category="Payments", type="Adyen",
       urlscan_query="domain:checkoutshopper-live.adyen.com", publicwww_query='"adyen.com"',
       verify_fingerprints=["adyen.com", "adyen"], exclude_hosts=["adyen.com"]),
    _r(id="authorizenet", category="Payments", type="Authorize.net",
       urlscan_query="domain:accept.authorize.net", publicwww_query='"authorize.net"',
       verify_fingerprints=["accept.authorize.net", "authorize.net"], exclude_hosts=["authorize.net"]),
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
