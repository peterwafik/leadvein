# UX Overhaul: Unified Find-Leads Journey — Design

Date: 2026-07-03
Status: user-approved direction (nav = one entry with modes inside; geo dataset = GeoNames snapshot). Spec pending user review.
Design preview artifact: https://claude.ai/code/artifact/33d4908c-a9cb-42dd-b0bb-63c6594c5714

## 1. Goal

Resolve the Composer/Campaigns/Marketplace tab confusion into one coherent guided journey; make geography and business-type controls complete AND honest; add a plain-language campaign builder; surface per-lead quality tiers; apply the design system consistently. Every existing compliance/honesty guarantee stays intact. No faked coverage, contacts, or verification claims.

## 2. Information architecture

### Navigation (buyer)

```
FIND LEADS
  Dashboard
  Find leads            → /app/find   (ONE entry point)
  Saved audiences       → /app/audiences
MANAGE
  Purchased leads · Suppression · Billing & credits   (unchanged)
```

- **Find leads** contains three clearly-labeled ways in, on one page-set:
  - **Campaigns (default view):** template gallery (utilities_uk, online_ordering, shopify_uk, business_restructuring) + "Describe your own" → the 5-step builder.
  - **Quick search (mode tab):** the simple filter set (business types, area, quality, freshness, contact requirements) that jumps straight to results. Absorbs Marketplace.
  - **Edit targeting (advanced) (inline disclosure):** the full predicate composer (available/sparse predicates, negation, tech recipes, coverage %) expands in-page inside step 2 and the Review step. Absorbs Composer. Never a separate destination.
- **Saved audiences** merges Segments and legacy Recipes into one list. Opening one re-enters the flow at the Estimate step with targeting loaded.

### Route changes

| Old | New behavior |
|---|---|
| `/app/marketplace` (+ `/search`) | redirect → `/app/find?mode=quick` |
| `/app/composer` (+ `?campaign=`, `?segment=`) | redirect → `/app/find` step 2 / loaded audience |
| `/app/campaigns` | redirect → `/app/find` |
| `/app/campaign-preview` | removed (flow is now real) |
| `/app/recipes` (GET/POST) | removed; existing LeadRecipe rows surfaced read-only in Saved audiences |
| `/app/segments` | redirect → `/app/audiences` |
| JSON endpoints `/app/composer/estimate`, `/apply-campaign`, `/save` | kept (renamed under `/app/find/*`, old paths aliased) |

### The 5-step flow

1. **Campaign** — pick a template or "Describe your own". Plain-language cards; honesty badges ("Ready today" / "Requires licensed source" traits).
2. **Where** — the new geography control (§3).
3. **Who** — business-type + technology multi-select (§4).
4. **Quality bar** — contact channel needed (phone / email / either), minimum quality tier, freshness. Plain labels; maps to quality profiles the serve-gate (INV-Q1) already enforces.
5. **Review & run** — plain-language sentence of what will run, gated-trait notices, live estimate (count + score/freshness distributions + masked samples via existing estimate endpoint), "Edit targeting (advanced)" disclosure, then Run → results grid (unlock cards) + "Save as audience".

Quick search enters at step 2's controls arranged as a single form and renders results immediately; same components, same honesty rules.

## 3. Geography control (two-layer, honest)

### Reference data

- New `geo_ref` table populated from a **GeoNames snapshot**: `countryInfo.txt` (countries), `admin1CodesASCII.txt` (regions/states), `cities1000.txt` (towns/cities ≥1k population, ~140k rows). License **CC BY 4.0** — attribution added to the provenance/attribution surface alongside ODbL.
- Schema: `geoname_id, country_code (ISO2), country_name, admin1_code, admin1_name, name, ascii_name, population`.
- Import via `scripts/import_geonames.py` (downloads from download.geonames.org, idempotent). A small committed fixture (~200 rows covering GB/US/DE test areas) seeds tests and first-run dev so nothing depends on network (mirrors INV-15 spirit).

### Live coverage

- Coverage counts computed from inventory: `GROUP BY country / (country, region) / (country, city)` over serveable leads, case-insensitive match of `Lead.city` ↔ `geo_ref.ascii_name` (and region ↔ admin1 name). Cached in-process with short TTL; recomputed with ingest.
- Inventory cities that don't match geo_ref are still listed (under "Other areas in inventory") — nothing hides.

### Endpoints

- `GET /app/geo/countries` → `[{code, name, lead_count}]` (all countries; counts honest, mostly 0).
- `GET /app/geo/areas?country=GB&q=oxf` → grouped `[{admin1_name, areas: [{name, kind: region|city, lead_count}]}]`, search over ascii_name/name, capped + ranked (leads first, then population).

### UI behavior

- Layer 1: searchable country list with lead counts ("United Kingdom — 143 leads", "Germany — 0 · not yet ingested").
- Layer 2: searchable region/town list grouped by region, each row: checkbox, name, coverage badge ("34 leads" / "0 · not yet ingested").
- Multi-select chips + a "Whole country" scope option (mutually exclusive with area chips per country).
- Zero-lead areas are selectable; the estimate then honestly shows 0 and the empty state explains why. Buyers see "not yet ingested"; **admins** additionally see "Request ingest" which queues an `IngestRequest (id, country, area, requested_by, status, created_at)` row surfaced on the admin ingest page. No silent empty results, no fake coverage.

### Compilation

Selections map to existing predicates only: `geo.country_any` (whole-country scopes), `geo.region_any` (region rows), `geo.city_any` (town rows), OR-combined within geography. No new engine predicate surface.

## 4. Business-type control (data-driven, complete)

One searchable, scrollable, grouped multi-select with visible checkmarks and chips:

- **Business categories** — live from `LeadCategoryLink` distinct keys with per-category lead counts; grows with ingestion. Never a hardcoded list.
- **Technology signals** — every fingerprint recipe from the library, grouped by recipe category. `enabled=True` recipes selectable with confidence badge ("strong signal"); `enabled=False` greyed with "test before use" (admin can precision-test/promote — existing flow). Selecting maps to `web.runs_tech {recipe_in, min_strength}` (default min_strength 1; advanced disclosure exposes the slider).
- **Gated traits** — campaign traits requiring a licensed source (e.g. financial distress) render greyed with "requires licensed source", never selectable, never faked (from `gated_signals`).

## 5. Campaign builder (plain language → targeting)

- Each step is one question with helper text and sensible defaults (copy in the preview artifact). No predicate keys, no "min score" — quality tiers are "Any / Good / Strong / Best" mapping to score bands, contact channel is "phone / email / either" mapping to `contactability.*` + quality profile.
- **Templates** prefill answers via existing `param_schema`/`compile_campaign` (placeholder substitution, list-slot expansion, gated notices — unchanged).
- **Describe your own** builds the same answer set from blank; a new server endpoint `POST /app/find/compile` accepts the plain answers and returns `{composition, quality_profile_key, sentence, gated_notices}`. For templates it delegates to `compile_campaign`; for custom it assembles the composition from the same vocabulary (geo predicates + category.any + web.runs_tech + contactability + quality.min_score + freshness.verified_within).
- **Plain-language sentence** is generated server-side from the composition (deterministic renderer over known predicate keys: "We'll find {categories} that run {tech}, in {areas}, with a {contact requirement}, verified within {freshness}"). Shown at Review before running; estimate reuses `/app/composer/estimate` (count, distributions, masked samples).
- Quality profiles: add three generic registered profiles — `phone_validated`, `email_validated`, `contact_validated` (business_contact) — so the contact-channel answer maps to a real enforced profile. Existing `baseline`/`utilities` unchanged.

## 6. Per-lead quality visibility

- Lead cards (results, estimate samples, purchased) show tier chips per field from `validation_json`: Phone/Email/Address/Website/Profile with tier (Present / Validated) and what the claim means ("format + line type", "syntax + MX", "geocoded", "reachable").
- **Verified-live** always renders as a locked, greyed chip "requires licensed provider" until such a provider is connected; Validated is never rendered as Verified-live (INV-Q2).
- Fingerprint leads additionally show match strength ("GloriaFood · 3 of 5 signals confirmed on their own homepage").
- Campaign quality bar sets the minimum tier via profile; the serve gate keeps enforcing it (INV-Q1). Absent fields say "not yet available", never inferred.

## 7. Visual polish

- All new screens use the existing design system (components.html macros + tokens); extend macros where needed (stepper, coverage badge, tier chip, grouped multiselect) rather than one-off styles.
- Every control has label + helper; loading, empty, zero-result and error states are designed (zero states say what to change); hover/focus states throughout.
- No engine jargon anywhere buyer-facing.
- Browser-verified via Playwright MCP against the running app (each step, geo search, greyed states, redirects, quality chips) — not just diff review.

## 8. Invariants preserved (unchanged and re-tested)

Business-entity data only (INV-11); masking on previews; quality serve gate (INV-Q1); no self-generated verified_live (INV-Q2); no SMTP probing (INV-Q6); grep-clean core (quality + fingerprint grep tests, extended to geo: no GeoNames/vendor strings in `app/core`); suppression/opt-out/retention filters in estimate and results; ODbL + CC BY 4.0 attribution and per-field provenance; greyed-not-faked for unconnected sources, low-confidence recipes, licensed-only traits; fingerprint own-homepage confirmation (INV-12), multi-signal strength (INV-13), dedup (INV-14), custom-only seeds / no network in seed paths (INV-15).

## 9. Testing

- Unit: geo_ref import (fixture), area search + coverage counts (0-lead honesty), compile endpoint (templates + custom + gated notices + sentence renderer), new quality profiles, redirects.
- Invariant additions: an un-ingested area estimate returns count 0 with honest empty state (never sample leads); tier chips never render verified_live from self-run validation; greyed recipes not selectable.
- Grep-clean: extend to keep `app/core` free of geonames/geo-vendor strings.
- Browser: Playwright pass over the full journey (template → run, describe-your-own → run, quick search, saved audience reopen, admin ingest-request).

## 10. Out of scope

Payments (parked), Wappalyzer fork-sync (license-gated, deferred), licensed verification providers (UI shows locked tier only), any new data sources.
