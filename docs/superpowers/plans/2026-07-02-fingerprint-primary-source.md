# Fingerprint Discovery as Primary Source — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use `- [ ]`.

> 🛑 **PAUSE after this plan for user review.** Per §K decisions: **custom recipes only** (NO Wappalyzer
> sync in this build — deferred, license-gated, verified in a PARALLEL research task); **high-confidence
> set only** (ambiguous recipes seeded greyed/disabled until Test-recipe proves precision — do NOT wire
> Stripe/PayPal/GA-style common tokens); **online-ordering (GloriaFood + ChowNow) is the first campaign**.
> Hold §E accuracy exactly — do NOT loosen to inflate counts. Payments parked; UK utilities demand test
> is the gate.

**Goal:** Promote the in-repo fingerprint engine (`app/engine/recipes|discover|enrich`) from a secondary
`tech_detection` adapter to a **co-equal PRIMARY discovery source** beside OSM — data-driven from a
recipe catalog (custom high-confidence recipes), wired through the existing quality gate / masking /
suppression / ODbL / audit / cross-source dedup, composable via a `web.runs_tech` predicate, with an
online-ordering campaign and a Test-recipe admin tool. Spec: `2026-07-02-fingerprint-primary-source-design.md`.

**Architecture:** A recipe catalog lives OUTSIDE core (`app/fingerprints/`, like `app/campaigns/`). A
`FingerprintDiscoveryAdapter` (a `LeadSourceAdapter`) runs any ENABLED recipe via the existing
`discover_urlscan`/`analyse` (mocked in tests), records **match strength** + matched recipe, and produces
`NormalizedLead`s that flow through the SAME ingest→gate→mask→dedup path as OSM. A `web.runs_tech`
predicate makes "runs Shopify" a composition leaf; `compile_campaign` maps a campaign's recipe categories
to a recipe-discovery + geo + quality composition. Cross-source dedup merges OSM + fingerprint into one
lead with per-field provenance. **No vendor/recipe strings in `app/core`.**

**Tech Stack:** Python 3.11 (`.venv/Scripts/python`), FastAPI/SQLModel, `requests` (mocked), pytest,
Jinja+Tailwind (shipped design system). Reuses the engine, adapter registry/waterfall/provenance, the
quality gate, geo_any predicates, the Campaign layer, the composer.

## Global Constraints
- Interpreter `.venv/Scripts/python`; tests `.venv/Scripts/python -m pytest`. Bash for git; no `cd`. Do NOT
  commit `*.db`. Pilot server holds `leadvault.db` — do NOT `rm` it; suite uses a temp DB.
- **§K1 — custom recipes only in THIS build.** No live Wappalyzer sync. The sync module is a LATER,
  license-gated increment; a parallel research task verifies a permissive fork + reports the exact fork +
  license before it is ever wired. Recipes here are hand-built custom data.
- **§K2 — high-confidence only, grey the rest.** Seed the ~20–25 dedicated-asset-domain recipes as
  `confidence="high", enabled=True`. Seed ambiguous ones (self-hosted / ubiquitous / separate-domain:
  WordPress, WooCommerce, Magento, Gravity Forms, GA/Meta/Ads, Stripe, PayPal, Toast, Olo) as
  `confidence="low", enabled=False` — greyed "test before use", NOT run in discovery. A recipe leaves grey
  only after Test-recipe (§Task 6) proves live precision. Do NOT wire common/ubiquitous tokens now.
- **§E accuracy (hold exactly, do NOT loosen):** multi-signal match strength; fingerprint required on the
  business's OWN homepage (not merely referenced); vendor/asset domains excluded (`exclude_hosts`);
  cross-source dedup (one business = one lead). Prefer a smaller on-target pool over inflated counts.
- **Honesty spine (unchanged):** masking, quality gate (**INV-Q1**), suppression/opt-out, ODbL + per-field
  provenance, audit, the **US DNC/TCPA hold-gate** all apply to fingerprint leads exactly as to OSM. No
  fabrication — analyse returns real page-derived values or the lead is dropped. Business-entity fields
  only; clearly-personal fields stay gated.
- **Grep-clean core (INV-9 extended):**
  `grep -rinE "gloriafood|chownow|shopify|fbgcdn|ewm2|data-glf|wappalyzer|urlscan|publicwww" app/core/` →
  empty. Recipe/vendor strings live in `app/fingerprints/` + `app/engine/` + `app/adapters/` + DB rows —
  never `app/core`. (Note: the pre-existing buyer `LeadRecipe` "saved search" in core is unrelated and
  stays.)
- Adapters mockable/offline — NO live urlscan/publicwww/homepage fetches in the suite. TDD; frequent commits.

## File Structure
```
app/fingerprints/__init__.py
app/fingerprints/models.py     # FingerprintRecipe (lv_fingerprint_recipe) — OUTSIDE core (like campaigns)
app/fingerprints/catalog.py    # CUSTOM high-confidence recipes + greyed low ones — vendor strings HERE
app/fingerprints/library.py    # list_recipes(category/confidence/enabled), get_recipe, seed_recipes, test_recipe
app/adapters/providers/fingerprint_discovery.py  # FingerprintDiscoveryAdapter (LeadSourceAdapter) — PRIMARY
app/adapters/dedup.py          # cross-source dedup + per-field provenance merge
app/targeting/predicates/web.py    # + web.runs_tech (matched recipe ids + min match strength)
app/campaigns/seed.py + compile.py # online-ordering campaign + recipe_categories -> recipe-discovery composition
app/engine/*                   # existing discover/enrich — reused, generalized per recipe
app/web/routes_admin.py + templates ; routes_buyer.py + composer.html  # sync/Test-recipe admin ; Technology group
tests/test_fingerprint_*.py
```

---

### Task 1: Recipe catalog model + library + seed high-confidence custom recipes
**Files:** Create `app/fingerprints/{__init__,models,catalog,library}.py`; Modify `app/leadvault.py`
(import model before init_db + seed at startup); Test `tests/test_fingerprint_library.py`.
**Produces:** `FingerprintRecipe(lv_fingerprint_recipe: id, recipe_key unique, category, tech_type,
urlscan_query, publicwww_query, verify_fingerprints_json, id_extractors_json, exclude_hosts_json,
confidence[high|medium|low], enabled bool, source[custom], license, synced_at)`. `library.list_recipes(
session, *, enabled=None, category=None) -> list`; `get_recipe(session, recipe_key)`; `seed_recipes(
session) -> int` (idempotent upsert from `catalog.CUSTOM_RECIPES`; custom rows never clobbered).
`catalog.CUSTOM_RECIPES` seeds:
  - **enabled high-confidence** (the online-ordering + ~20–25 dedicated-asset set): **gloriafood** (verbatim
    from `app/engine/recipes.py` BUILTIN — fbgcdn.com/ewm2.js/data-glf-ruid/data-glf-cuid + ruid/cuid
    extractors), **chownow**, shopify (`cdn.shopify.com`), bigcommerce, wix (`wixstatic.com`), squarespace
    (`static1.squarespace.com`), webflow (`website-files.com`), duda (`irp.cdn-website.com`), calendly
    (`assets.calendly.com`), intercom (`widget.intercom.io`), zendesk (`static.zdassets.com`), tawkto
    (`embed.tawk.to`), crisp (`client.crisp.chat`), drift (`js.driftt.com`), freshchat
    (`wchat.freshchat.com`), livechat (`cdn.livechatinc.com`), klaviyo (`static.klaviyo.com`), hubspot
    (`js.hs-scripts.com`), marketo (`munchkin.marketo.net`), hotjar (`static.hotjar.com`), segment
    (`cdn.segment.com`), trustpilot (`widget.trustpilot.com`), yotpo (`staticw2.yotpo.com`), typeform
    (`embed.typeform.com`), jotform (`form.jotform.com`), klarna (`x.klarnacdn.net`). Each with a domain:
    urlscan_query, a publicwww_query, verify_fingerprints (asset host + a DOM/token), exclude_hosts (the
    vendor's own domain), confidence="high", enabled=True.
  - **greyed low-confidence** (seed but `enabled=False`, `confidence="low"`): wordpress, woocommerce,
    magento, prestashop, gravityforms, google_analytics, meta_pixel, google_ads, stripe, paypal, toast,
    olo — with a note the discovery token is generic/self-hosted/separate-domain (test before use).
- [ ] **Step 1: Failing test** — `seed_recipes` idempotent; `list_recipes(enabled=True)` includes
  `gloriafood`+`chownow`+`shopify` and EXCLUDES `stripe`/`wordpress`/`google_analytics` (greyed); a greyed
  recipe has `confidence=="low"` and `enabled==False`; `get_recipe("gloriafood")` carries the ruid/cuid
  extractors verbatim.
- [ ] Steps 2–4 (fail→implement→pass + suite; wire model import + `seed_recipes` at startup like campaigns).
- [ ] **Step 5: grep gate** (`tests/test_fingerprint_grepclean.py`): the vendor pattern above finds nothing
  in `app/core/**/*.py`.
- [ ] **Step 6: Commit** `feat(fingerprints): recipe catalog model + library + seed high-confidence custom recipes (greyed low-confidence)`

### Task 2: FingerprintDiscoveryAdapter (primary source) + match strength
**Files:** Create `app/adapters/providers/fingerprint_discovery.py`; Modify `app/adapters/providers/__init__.py`
(register); Test `tests/test_fingerprint_discovery.py`.
**Produces:** `FingerprintDiscoveryAdapter` (`LeadSourceAdapter`), `meta=SourceMeta(key="fingerprint",
name="Technology fingerprint", type="fingerprint_discovery", ..., terms_status="permitted",
key_env="" (urlscan free default; URLSCAN_KEY optional raises limits), rate_limit={...})`. `discover(query,
*, discover_fn=engine_discover)`: for the query's `recipe_key` (or all ENABLED recipes for a category),
run discovery (mocked in tests), yield `{host, recipe_key}`. `normalize(raw, *, fetch_fn=engine_fetch)`:
fetch the host's OWN homepage, `analyse(recipe, url, html)` → confirm ≥1 `verify_fingerprint` present
(**own-homepage confirmation, INV-12**; drop if none), compute **match_strength = count of matched
fingerprints**, build `NormalizedLead` (business_name/email/phone/website/category from recipe;
`attributes={matched, match_strength, recipe_key, tech_type, on_platform}`), source_key="fingerprint",
license = urlscan attribution. Vendor/asset hosts excluded via `exclude_hosts`.
- [ ] **Step 1: Failing test** (mocked discover_fn + fetch_fn — NO network): a canned homepage HTML
  containing the gloriafood asset host + `data-glf-ruid` → normalize yields a NormalizedLead with
  `match_strength>=2`, `matched` listing both, the ruid extracted; a homepage that only LINKS to the
  vendor (fingerprint absent from own page) → normalize returns None (INV-12); a vendor's own domain in
  discovery results is excluded.
- [ ] Steps 2–4. **Step 5: Commit** `feat(adapters): FingerprintDiscoveryAdapter primary source + multi-signal match strength (own-homepage confirmation)`

### Task 3: Ingest through the gate + cross-source dedup + provenance
**Files:** Create `app/adapters/dedup.py`; Modify the ingest path (`app/ingestion/pipeline.py`) to accept
fingerprint-sourced NormalizedLeads and dedup; Test `tests/test_fingerprint_ingest_dedup.py`.
**Produces:** `dedup.merge_or_create(session, normalized, *, source_key, license) -> Lead` — compute the
existing `dedupe_key` (domain/name+geo); if a Lead exists, MERGE gap-fill fields with **per-field
provenance** (`field_provenance_json`, waterfall rules — don't overwrite verified) and return it; else
create. Fingerprint leads run the SAME `build_validation`/gate/masking downstream.
- [ ] **Step 1: Failing test** —
  - **INV-Q1:** a fingerprint lead with no validated contact does NOT surface in search/estimate and can't
    be unlocked; a fingerprint lead with a validated phone surfaces (hot).
  - **INV-14 dedup:** the same business ingested via OSM (address/category) then fingerprint (website/tech)
    → ONE Lead; `field_provenance_json` shows OSM for address, fingerprint for website/tech; not two rows.
  - masking hides the fingerprint-derived email/phone on a masked card; ODbL/ provenance intact.
- [ ] Steps 2–4. **Step 5: Commit** `feat(fingerprints): fingerprint leads through gate/mask + cross-source dedup with per-field provenance (INV-Q1/INV-14)`

### Task 4: `web.runs_tech` predicate + composer Technology group
**Files:** Modify `app/targeting/predicates/web.py`, `app/targeting/runtime.py`, `app/web/templates/composer.html`,
`app/web/routes_buyer.py`; Test `tests/test_web_runs_tech.py`.
**Produces:** `web.runs_tech` predicate — params `{"recipe_in":[recipe_key...], "min_strength":int}`; reads
the lead's `attributes.recipe_key`/`match_strength`; matches True if the lead's recipe ∈ `recipe_in` and
`match_strength >= min_strength`, tri-state None when absent. Composer gets a **"Technology"** group
(data-driven from `list_recipes(enabled=True)` grouped by category; greyed recipes shown disabled "test
before use") that emits a `web.runs_tech` node.
- [ ] **Step 1: Failing test** — predicate matches a lead running gloriafood with strength≥2 and a
  min_strength filter; excludes a lead of another recipe; None when the lead has no recipe. (UI verified in
  Task 7 browser pass.)
- [ ] Steps 2–4 + parse-check templates. **Step 5: Commit** `feat(targeting): web.runs_tech predicate + composer Technology group (data-driven, greyed low-confidence)`

### Task 5: Online-ordering campaign + campaign→recipe mapping
**Files:** Modify `app/campaigns/seed.py`, `app/campaigns/compile.py` (+ `app/campaigns/models.py` if a
`recipe_categories` field is needed); Test `tests/test_campaign_recipe.py`.
**Produces:** Campaign gains `recipe_categories`/`recipe_ids` (data). `compile_campaign` composes a
`web.runs_tech` node (from the campaign's recipe ids) + geo + contactability + quality into the v2
composition. Seed **"Online ordering upgrades"** (recipe_ids gloriafood+chownow; param area; quality
profile baseline/utilities). "Shopify stores (UK)" may be seeded as a second (recipe shopify + geo GB).
- [ ] **Step 1: Failing test** — compiling the online-ordering campaign with {area} yields a composition
  whose nodes include `web.runs_tech {recipe_in:["gloriafood","chownow"], ...}` + `geo.city` + a contact
  predicate; gated_notices empty; INV-8 (no single OSM category pin unless declared).
- [ ] Steps 2–4. **Step 5: Commit** `feat(campaigns): online-ordering tech campaign + campaign->recipe compilation`

### Task 6: Test-recipe admin tool + grey/promote + credit visibility
**Files:** Modify `app/fingerprints/library.py` (`test_recipe`), `app/web/routes_admin.py`,
`app/web/templates/admin_sources.html`; Test `tests/test_recipe_precision.py`.
**Produces:** `library.test_recipe(session, recipe_key, *, discover_fn, fetch_fn, n=5) -> {tested, matched,
precision, samples}` — discover ~n candidates, verify each on its OWN homepage, report match rate +
sample business contacts (mocked in tests). Admin: a per-recipe **"Test recipe"** button (shows precision +
samples) BEFORE any bulk run; low-confidence recipes rendered greyed "test before use" and only
promotable (enable) after a passing test; the sources view shows urlscan/publicwww credit/rate + the
fingerprint source. (Sync-fingerprints button is DEFERRED — a stub that says "custom recipes only; fork
sync pending license verification".)
- [ ] **Step 1: Failing test** — `test_recipe` with a mocked discover returning 5 hosts (3 verify on their
  own homepage, 2 don't) → `precision==0.6`, `matched==3`, samples carry business-entity contacts only.
- [ ] Steps 2–4 + parse-check. **Step 5: Commit** `feat(fingerprints): Test-recipe precision tool + grey/promote gating + admin credit visibility`

### Task 7: INV-11..15 tests + grep-clean + whole-branch review prep
**Files:** Test `tests/test_fingerprint_invariants.py`; extend the grep test.
- [ ] **INV-11 business-entity only:** analyse/normalize never populate clearly-personal fields; only
  business-entity fields on the NormalizedLead.
- [ ] **INV-12 own-homepage:** re-assert a referenced-but-not-present fingerprint is not a match.
- [ ] **INV-13 multi-signal:** match_strength recorded; a `min_strength` filter drops single-weak-token
  leads; a greyed recipe is not run by discovery.
- [ ] **INV-14 dedup:** one business across OSM+fingerprint = one lead, merged provenance (re-assert).
- [ ] **INV-15 sync license:** the sync path is NOT wired (custom-only); assert no live-sync code path runs
  + the catalog is `source=="custom"`.
- [ ] **grep-clean core** empty for the vendor pattern. Full suite + parse + grep green.
- [ ] **Commit** `feat(fingerprints): INV-11..15 + grep-clean tests for fingerprint-sourced leads`

## PARALLEL (separate, non-blocking): Wappalyzer fork license verification
Dispatch a research task to identify a genuinely permissive Wappalyzer-format fingerprint fork (e.g.
`enthec/webappanalyzer`), confirm its CURRENT license permits redistribution/derivative use, and record
the exact fork + license + a snapshot ref. **Report to the user BEFORE the sync increment is built.** If
none qualifies → stay custom-only. This does NOT gate Tasks 1–7.

## Self-Review
**Coverage (§A–G + §K):** custom high-confidence recipes as data, greyed low-confidence (K1/K2, T1);
fingerprint as PRIMARY source with match strength + own-homepage confirmation (§D/§E1/§E4, T2); through the
gate/mask/dedup with per-field provenance (§E5, T3, INV-Q1/12/14); composable `web.runs_tech` + Technology
UI group (§E3/§F, T4); online-ordering campaign→recipe compilation (§E2, T5, K3); Test-recipe precision +
grey/promote + credits (§F, T6); INV-11..15 + grep-clean (§G, T7). Sync deferred + license verified in
parallel (K1). Ubiquitous/common tokens NOT wired (K2). Accuracy not loosened (§E held).
**Deferred (NOT built):** the Wappalyzer fork-sync increment (license-gated); promoting greyed recipes
(only via Test-recipe precision); Shopify-UK campaign is optional-second. **Placeholder scan:** backend +
tests carry full code; catalog asset domains are concrete; UI (T4/T6) is a design-system contract browser-
verified in T7. **Types:** `web.runs_tech {recipe_in:[],min_strength}` matches the lead
`attributes.recipe_key/match_strength`; dedup uses the existing `dedupe_key` + `field_provenance_json`.

**🛑 After this plan: PAUSE for user review. Fork-sync is a later, license-gated increment. Payments parked;
UK utilities demand test is the gate.**
