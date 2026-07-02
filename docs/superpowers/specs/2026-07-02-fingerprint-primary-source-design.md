# Fingerprint Discovery as a First-Class Primary Source — Design Spec

**Date:** 2026-07-02 · **Status:** 📋 SPEC for review — **do NOT build until approved.** Extends the
locked Targeting v2, Campaign-layer, and Waterfall-enrichment specs. Payments parked; UK utilities demand
test remains the real gate.

**The insight (founding):** "find every business running technology X" scales to real volume lawfully,
because public fingerprint indexes (urlscan, publicwww) already crawled the web. The engine that proves it
already exists in-repo (`app/engine/recipes.py|discover.py|enrich.py`, the GloriaFood recipe verbatim).
This spec **promotes** that engine from a secondary `tech_detection` adapter to a **co-equal primary
discovery source** beside OSM, makes the fingerprint library **synced not hardcoded**, broadens category
coverage, and adds **campaign-relevance + accuracy** so volume is on-target, not noise.

---

## 0. What already exists (we extend, not rebuild)
- `Recipe` dataclass = `{id, category, type, urlscan_query, publicwww_query, verify_fingerprints[],
  id_extractors{}, exclude_hosts[], logo, is_builtin}` — **exactly** the abstraction requested.
- `discover_urlscan` (search_after paging, 429 backoff, optional `URLSCAN_KEY`), `discover_publicwww`
  (`PUBLICWWW_KEY`), `discover_meta`; `analyse()/fetch()/norm_url()` (homepage fetch, first-match verify,
  name/email/phone/id extraction); `UrlscanFingerprintAdapter` (a `LeadSourceAdapter`).
- `BUILTIN_RECIPES` (GloriaFood, ChowNow, Flipdish, Shopify, WooCommerce, BigCommerce, Magento, Wix,
  Squarespace, …) — these become the **custom/seed layer**, additive on top of the synced library.
- The waterfall + per-field provenance + feature-flag registry + budget + US hold-gate + geo_any + Campaign
  layer are all in place to plug into.

---

## A. Fingerprint library — SYNCED, not hardcoded

**A hand-written list rots.** So the library is DATA, refreshed from an open-source fingerprint corpus.

### A.1 Sync source + 🚩 LICENSE FLAG (must resolve before building)
- Wappalyzer's canonical repo **relicensed to a proprietary/commercial license (~2023)** — we must NOT
  sync from it. Sync instead from a **permissively-licensed community continuation** of the Wappalyzer-
  format fingerprints (e.g. `enthec/webappanalyzer`, MIT-style) — **but the exact fork + its current
  license must be verified before building.** Store the source name, license, and commit/version we synced
  from, and show attribution in admin. If no fork with a clearly-permissive license exists at build time,
  we fall back to **our own custom recipes only** (still real, just smaller) rather than sync something we
  can't lawfully redistribute.
- Wappalyzer JSON shape → our `Recipe`: `technologies/*.json` entries carry `cats`, `html`, `scriptSrc`,
  `js`, `meta`, `headers`, `cookies`, `implies`, `website`, `icon`. Map: `scriptSrc`/`html`/`meta`/
  `headers`/`cookies`/`js` regexes → `verify_fingerprints`; `cats` → our `category`; `website`/`icon` →
  provenance/logo. **`discovery_query` is NOT in Wappalyzer** — see A.3.

### A.2 Storage + refresh
- New generic table `lv_fingerprint_recipe` (recipe data — **no vendor strings in `app/core`**; the table
  is generic, the rows are data). Fields mirror `Recipe` + `source` (wappalyzer-fork | custom), `license`,
  `synced_at`, `discovery_confidence` (high|medium|low), `enabled`.
- **Admin "Sync fingerprints" job:** fetch → parse → upsert rows (custom recipes never overwritten),
  stamp source/license/version. Idempotent; re-runnable to stay current.
- **Custom recipes stay additive & authoritative:** GloriaFood (fbgcdn.com / ewm2.js / data-glf-ruid /
  data-glf-cuid + ruid/cuid extractors) and any we author live in `app/fingerprints/catalog.py`
  (strings HERE, not core) and are seeded/merged on top — a sync never clobbers them.

### A.3 The discovery_query gap (the honest part)
Wappalyzer gives the **verify** fingerprint but not an **index-searchable discovery token** (the asset
domain to search in urlscan/publicwww). The sync **derives** a candidate discovery token from the tech's
`scriptSrc` asset host (e.g. Shopify→`cdn.shopify.com`) and assigns a **confidence**:
- **high** — a dedicated, distinctive asset domain (discovery works out of the box).
- **medium** — an asset domain that works but is noisier / less distinctive (tune + Test-recipe).
- **low** — self-hosted tech (no shared asset domain) or a ubiquitous token (returns the whole web) →
  **greyed until you Test-recipe**; discovery may need publicwww content-search or a different signal.
See §B for the per-recipe confidence report.

---

## B. Category catalog + honest per-recipe confidence

Recipes are organized by CATEGORY so a campaign targets the tech its ideal customers run. The requested
categories are seeded; **exact fingerprint tokens come from the synced library, not from memory.** The
**discovery** confidence below is my honest assessment of whether asset-domain discovery works out of the
box (H), needs tuning/testing (M), or won't target well without a different signal (L — Test-recipe first).

| Category | High-confidence (H) — work out of the box | Medium (M) — test/tune the token | Low (L) — FLAG, Test-recipe / needs different signal |
|---|---|---|---|
| Online ordering / restaurants | **GloriaFood** (proven) | ChowNow, Flipdish, Square Online | **Toast**, **Olo** (usually a *separate* ordering domain, not on the restaurant's own homepage) |
| E-commerce | Shopify (`cdn.shopify.com`), BigCommerce (`cdn11.bigcommerce.com`), Wix Stores, Squarespace Commerce | PrestaShop, Square Online | **WooCommerce**, **Magento** (self-hosted → no shared CDN; content-search only, noisy) |
| Website builders / CMS | Wix (`wixstatic.com`), Squarespace (`static1.squarespace.com`), Webflow (`website-files.com`), Duda (`irp.cdn-website.com`) | GoDaddy (`img1.wsimg.com`), Weebly (`editmysite.com`) | **WordPress** (self-hosted; `wp-content` on own domain — huge volume, weak targeting) |
| Booking / scheduling | Calendly (`assets.calendly.com`) | Acuity, Cal.com, Mindbody, Setmore, SimplyBook | — |
| Payments / checkout | Klarna (`x.klarnacdn.net`) | Square, Afterpay/Clearpay, Adyen, Mollie, GoCardless | **Stripe** (`js.stripe.com`), **PayPal** — work but *very* common → weak alone; only useful combined with geo+category |
| Marketing / email / CRM | HubSpot (`js.hs-scripts.com`, `js.hsforms.net`), Klaviyo (`static.klaviyo.com`), Marketo (`munchkin.marketo.net`) | Mailchimp, ActiveCampaign | — |
| Chat / support | Intercom (`widget.intercom.io`), Zendesk (`static.zdassets.com`), Tawk.to (`embed.tawk.to`), LiveChat (`cdn.livechatinc.com`), Crisp (`client.crisp.chat`), Drift (`js.driftt.com`), Freshchat (`wchat.freshchat.com`) | — | — |
| Analytics / pixels (intent) | Hotjar (`static.hotjar.com`), Segment (`cdn.segment.com`) | TikTok Pixel | **GA/GA4**, **Meta Pixel** — ubiquitous → useless as a *discovery* token; keep as **verify/intent signals only** |
| Ads / retargeting | — | TikTok | **Google Ads, Meta Ads, DoubleClick** — ubiquitous → verify/intent only |
| Reviews / trust | Trustpilot (`widget.trustpilot.com`), Yotpo (`staticw2.yotpo.com`) | Reviews.io, Feefo | — |
| Forms / lead capture | Typeform (`embed.typeform.com`), Jotform (`form.jotform.com`), HubSpot Forms (`js.hsforms.net`) | — | **Gravity Forms** (self-hosted WP plugin) |

**Bottom line:** roughly **20–25 recipes are high-confidence out of the box** (dedicated asset domains —
the e-commerce/builder/chat/booking/reviews/forms widgets). The **self-hosted platforms (WordPress,
WooCommerce, Magento, Gravity Forms)** and **ubiquitous pixels (GA, Meta, Ads)** are the honest weak spots:
they're great *verify/intent* signals but poor *discovery* seeds. **Stripe/PayPal** discover fine but only
target usefully when combined with geo+category. **Toast/Olo** need Test-recipe (separate-domain problem).

---

## C. Discovery at scale (generalize the proven engine)
- `discover_urlscan(recipe, ...)` already exists — generalize the adapter so ANY recipe's `urlscan_query`
  (asset domain / token) runs it: search_after paging, 429 backoff (**preserved verbatim**), dedup hosts,
  strip `www.`, drop `exclude_hosts` + the vendor's own infra. `URLSCAN_KEY` (`.env`) raises limits; free
  default with zero keys.
- `discover_publicwww(recipe, ...)` optional (`PUBLICWWW_KEY`, `.env`) — the recipe's `publicwww_query`,
  `/?export=urls` paging. Best for self-hosted tech (content search where there's no asset domain).
- Both **feature-flagged** (disabled-mode pattern): app runs on urlscan-free with zero keys.
- **🚩 ToS notes to hold:** urlscan's search API is used as intended (search the public scan index), but
  **bulk/commercial harvesting on the free tier is limited — heavy use needs their commercial plan**;
  respect rate limits + politeness. publicwww is a paid source-code-search API used for its stated purpose.
  Homepage-verify fetches read only the **business's own public homepage** (respect robots + politeness).

## D. Verify + enrich (reuse `analyse()`)
Per discovered domain: fetch its OWN homepage (retry trailing `/`), confirm any `verify_fingerprint`
present (**first-match-wins → records which matched**), extract business name (title → og:site_name/
og:title), business email (mailto + regex; drop image-ext + tracking domains, **dynamically** incl. the
recipe's asset/exclude hosts), business phone (tel: first, else regex), and any `id_extractors`.
**Business-entity fields only; clearly-personal fields stay gated.** This is `analyse()` generalized —
already implemented; we wire it through the primary adapter + the quality gate.

## E. Accuracy / campaign-relevance (the "smart + related" part)
1. **Multi-signal confidence:** record match strength = how many of a recipe's `verify_fingerprints`
   matched on the homepage (asset domain AND a DOM attribute > a single weak token). Store on the lead
   (`attributes.match_strength` + `matched[]`). A campaign/composition can **require a minimum** strength.
2. **Campaign → recipe mapping (extends Campaign spec):** a Campaign declares `recipe_categories` /
   `recipe_ids` that indicate its ideal customer. `compile_campaign` composes **recipe-discovery source +
   geo + quality** predicates → results are on-target *by construction*. E.g. "online-ordering upgrades" →
   restaurants on GloriaFood/ChowNow; "Shopify app" → Shopify stores in {area} with a valid phone.
3. **Composable with existing predicates:** fingerprint leads flow through the SAME targeting engine —
   `geo.*_any` (whole-country scope), category, contactability, freshness, the quality gate. A new
   **`web.runs_tech` predicate** (reads a lead's matched recipe ids + strength) makes "runs Shopify" a
   first-class composition leaf, so "Shopify stores in the UK with a valid phone" is ONE composition.
4. **False-positive guards:** exclude the vendor's own domains (`exclude_hosts`); require the fingerprint
   on the business's **own homepage** (not merely referenced elsewhere); flag recipes whose token is
   generic/ubiquitous (§B low tier) and **grey them until Test-recipe**; the Test-recipe job reports
   **per-recipe precision** (match rate on a live sample).
5. **Cross-source dedup:** a business found via BOTH OSM and fingerprint = **one** deduped lead (existing
   `dedupe_key` on domain/name+geo) with **merged per-field provenance** (the waterfall's
   `field_provenance_json`): OSM supplies address/category, fingerprint supplies website/tech + maybe
   email/phone — each field stamped with its source + license. Never two rows for one business.

## F. UI
- **Composer + Campaign:** fingerprint discovery is a **primary source** (a "Technology" targeting group),
  data-driven — categories/recipes come from what's actually **synced + enabled**; low-confidence recipes
  are **honestly greyed** ("needs Test-recipe") until proven. Guided (pick a campaign/category) + advanced
  (pick specific recipes + min match-strength).
- **Admin:** a **"Sync fingerprints"** job (source/license/version shown); a per-recipe **"Test recipe"**
  (~5 candidates → real match rate + sample business contacts) that must be run **before any bulk run**;
  per-source credit/rate visibility (urlscan/publicwww) in the existing sources view.

## G. Hard boundaries + invariants (new, additive)
- **INV-11 (business-entity only):** fingerprint discovery reads public business pages + business-entity
  fields only; no personal-individual profiling; clearly-personal fields stay gated.
- **INV-12 (own-homepage confirmation):** a fingerprint lead is confirmed only if the verify fingerprint is
  present on the business's OWN homepage; vendor/asset domains are excluded. **Test:** a page that merely
  links to the vendor is not a match.
- **INV-13 (multi-signal + Test-recipe gate):** match strength recorded; low-confidence recipes greyed
  until Test-recipe reports precision; a campaign may require a minimum strength.
- **INV-14 (cross-source dedup):** one business = one lead across OSM + fingerprint, merged per-field
  provenance. **Test:** the same domain from both sources yields one row with two field-sources.
- **INV-15 (sync license):** only a permissively-licensed fingerprint corpus is synced; source + license +
  version recorded + attributed; a ToS/license-incompatible source is refused (fall back to custom only).
- Inherits **INV-Q1** (gate — a fingerprint lead is "hot" only after clearing it), masking, suppression/
  opt-out, ODbL + per-field provenance, audit, the **US DNC/TCPA hold-gate**, and **grep-clean core**
  (recipe/vendor strings live in `app/fingerprints` + `app/engine` + `app/adapters` + DB rows — never
  `app/core`). Adapters mockable/offline in tests (no live urlscan/publicwww/homepage fetches in the suite).

## H. Module layout (what WOULD be built)
```
app/fingerprints/sync.py       # fetch permissive Wappalyzer-fork JSON -> parse -> upsert recipe rows (+license/version)
app/fingerprints/catalog.py    # seeded categories + CUSTOM recipes (GloriaFood etc.) — vendor strings HERE
app/fingerprints/library.py    # lv_fingerprint_recipe access: list by category/confidence/enabled; test_recipe(sample)
app/core/db.py                 # + lv_fingerprint_recipe (GENERIC table) ; Lead already has dedupe_key + field_provenance_json
app/adapters/providers/fingerprint_discovery.py  # FingerprintDiscoveryAdapter (LeadSourceAdapter) — PRIMARY source
app/engine/*                   # existing discover/enrich — generalized per-recipe (reused)
app/targeting/predicates/web.py    # + web.runs_tech predicate (matched recipe ids + min strength)
app/campaigns/                 # compile_campaign += recipe_categories -> recipe-discovery source + geo + quality
app/adapters/dedup.py          # cross-source dedup + per-field provenance merge
app/web/... + templates        # composer/campaign Technology group; admin sync + Test-recipe; grey low-confidence
```

## I. Proposed build sequence (subagent-driven, TDD — NOT started)
1. `lv_fingerprint_recipe` table + `library.py` (list/enable/confidence) + seed custom recipes (GloriaFood).
2. Sync job (`sync.py`) — permissive fork parse→upsert, license/version recorded (after the §A.1 license is
   confirmed). Admin "Sync fingerprints".
3. `FingerprintDiscoveryAdapter` (primary source) generalizing the engine per recipe; mocked discovery/fetch.
4. `web.runs_tech` predicate + match-strength on the lead; composer "Technology" group (data-driven, greyed
   low-confidence).
5. Campaign→recipe mapping in `compile_campaign` + a seeded tech-campaign.
6. Cross-source dedup + per-field provenance merge.
7. Test-recipe admin job (sample precision + sample contacts) + per-source credit visibility.
8. INV-11..15 tests + grep-clean + whole-branch review.

## J. Honest confidence summary (for your review)
- **High-confidence, ready to run once synced (~20–25 recipes):** the dedicated-asset-domain widgets —
  Shopify, BigCommerce, Wix, Squarespace, Webflow, Duda, Calendly, Intercom, Zendesk, Tawk.to, Crisp,
  Drift, Freshchat, LiveChat, Klaviyo, HubSpot(+Forms), Marketo, Hotjar, Segment, Trustpilot, Yotpo,
  Typeform, Jotform, Klarna — plus the proven **GloriaFood**.
- **Test-recipe first (I need your go on a live sample):** ChowNow, Flipdish, Square/Square Online,
  Acuity, Cal.com, Mindbody, Setmore, SimplyBook, GoDaddy, Weebly, Mailchimp, Afterpay/Clearpay, Adyen,
  Mollie, GoCardless, Reviews.io, Feefo, TikTok Pixel.
- **Weak as discovery seeds (verify/intent only, or need a different signal):** WordPress, WooCommerce,
  Magento, PrestaShop, Gravity Forms (self-hosted); GA/GA4, Meta Pixel, Google Ads, DoubleClick
  (ubiquitous); Stripe, PayPal (common → only with geo+category); Toast, Olo (separate ordering domain).

## K. Open decisions for you (before I build)
1. **Sync source/license:** OK to sync from a permissively-licensed Wappalyzer fork (I'll verify the exact
   fork + license and record it), with fallback to custom-only if none qualifies? Or custom-recipes-only to
   start (smaller, zero license risk)?
2. **Discovery scope for launch:** start with the ~high-confidence set only (grey the rest until
   Test-recipe), or also wire the Stripe/PayPal-style common tokens gated behind mandatory geo+category?
3. **First tech-campaign to seed** (for the demo): e.g. "Online-ordering upgrades → restaurants on
   GloriaFood/ChowNow" or "Shopify stores in the UK"?

**🛑 STOP for your review. No code until you approve §K. Business-entity only, ToS-respecting, honesty
spine intact, grep-clean core. Payments parked; UK utilities demand test is the gate.**
