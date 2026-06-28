# LeadVault — Slice One Design (Compliant B2B Lead Marketplace, MVP vertical)

**Date:** 2026-06-28
**Status:** Drafted in brainstorming; awaiting user review before writing-plans.
**Working name:** LeadVault (placeholder).

---

## 0. What this is (and is not)

LeadVault is a **compliant B2B lead-intelligence marketplace**. Buyers define exactly the
businesses they want, preview masked matches, spend credits to unlock full records, and export
— with source, license, verification, and compliance metadata on every lead.

The existing GloriaFood/tech-fingerprint scraper is **not the product**. It was the sample that
proved fingerprint detection generalizes. From here it is **one internal source/enrichment
adapter** behind a source-agnostic marketplace core.

**Slice one is the minimum coherent vertical**, end-to-end:
authenticated buyer journey → Lead Recipe Builder → masked preview → credit-unlock →
Purchased Leads + CSV export, plus admin-run inventory ingestion. (Public marketing site and
onboarding questionnaire are dropped for now.)

---

## 1. Non-negotiable architecture constraint: source- and category-agnostic

The whole point of the product is **ANY business, ANY website, ANY category** — not an
"OSM energy-leads tool". Slice one MUST NOT bake in a vertical. Concretely:

1. **Source adapters.** A `LeadSourceAdapter` interface (`discover` / `normalize` /
   `attribution`). OSM/Overpass is the **first** concrete adapter; the urlscan fingerprint
   engine is the **second**. Adding a future source = adding an adapter, never touching the
   marketplace core.
2. **Taxonomy is data, not enums.** Categories live in the DB (`LeadCategory` +
   `CategoryMapping`), are admin-editable, and are never hardcoded Python enums. Adapters map
   their source categories onto taxonomy keys.
3. **Scoring profiles are pluggable per vertical.** The core scorer is profile-agnostic.
   "Energy/utility" is **one seeded `ScoringProfile`** (`utility_energy`), registered like any
   other — not an assumption in the core.
4. **Grep discipline (enforced in the plan).** No `energy`, `utility`, `osm`, or `overpass`
   strings may appear in the marketplace **core** (recipes, credits, masking, purchase, export,
   taxonomy). Those belong only inside the relevant adapter (`app/adapters/osm.py`) or scoring
   profile (`app/scoring/profiles/utility_energy.py`) or seed data. The plan includes a grep
   acceptance check over `app/core/` and reports the result.

---

## 2. Stack

Evolve the current app — **no Node build**:
- **FastAPI + SQLModel/SQLite** (models written Postgres-ready; SQLite for slice one).
- **Jinja2 templates + Tailwind (CDN)** for a multi-page dashboard; small vanilla JS for
  interactivity (recipe builder, tables). Reuse the existing look.
- **Real lightweight auth:** email + password (hashed via `passlib`/bcrypt), signed session
  cookie, roles `buyer` / `admin`. Seeded admin.
- Reuse existing engine code (`app/engine/*`: discover, enrich, geo, politeness, export) as
  internal libraries behind adapters/enrichment. The old single-page Search/Jobs SPA is
  **superseded** by the new dashboard (its code stays in-repo but is unlinked from the product
  nav; not deleted in slice one).

---

## 3. Module layout

```
app/
  core/                      # SOURCE- and CATEGORY-AGNOSTIC marketplace core
    db.py                    # SQLModel entities + engine/session + seed
    auth.py                  # password hashing, sessions, role guards (buyer/admin)
    taxonomy.py              # LeadCategory CRUD + lookup (DB-driven, no enums)
    recipes.py               # LeadRecipe model + filter -> SQL query over Lead inventory
    marketplace.py           # search, estimate, masked preview projection
    masking.py               # server-enforced mask/unlock serializers
    purchasing.py            # credit ledger, unlock, ownership + re-buy guard
    export.py                # CSV export of purchased leads (reuses engine.export)
    compliance.py            # suppression/opt-out checks, attribution, audit log
  adapters/
    base.py                  # LeadSourceAdapter protocol, NormalizedLead, AdapterQuery, SourceMeta
    osm.py                   # Overpass adapter (FIRST concrete source)
    urlscan_fingerprint.py   # existing fingerprint engine wrapped as an adapter (SECOND)
    registry.py              # adapter registry (key -> adapter)
  enrich/
    website.py               # reachability + tech fingerprint enrichment (reuses engine.enrich)
  scoring/
    engine.py                # profile-AGNOSTIC scorer + generic sub-scores
    profiles/
      base.py                # ScoringProfile protocol
      utility_energy.py      # energy-usage profile (ONE of many)
      registry.py            # profile key -> profile
  ingestion/
    pipeline.py              # discover -> normalize -> dedup -> enrich -> score -> comply -> store
  engine/                    # EXISTING tech-fingerprint engine (reused internally; unchanged)
  web/
    templates/               # Jinja2 dashboard pages + shared layout
    deps.py                  # current-user / role dependencies
    routes_auth.py           # register / login / logout
    routes_buyer.py          # recipes, marketplace, purchased leads, exports, suppression, credits
    routes_admin.py          # ingestion, leads, sources, categories, opt-outs, audit log
  main.py                    # app wiring, startup seed, route mounting
```

> Naming note: the existing `engine/recipes.py` holds **fingerprint** recipes; the new
> `core/recipes.py` holds **buyer LeadRecipes** (saved searches). Different concepts, both kept.

---

## 4. The source adapter interface (the heart of source-agnosticism)

```python
# app/adapters/base.py  (sketch)
@dataclass
class SourceMeta:
    key: str            # "osm_overpass", "urlscan_fingerprint"
    name: str
    type: str           # "open_data", "tech_detection", ...
    url: str
    license: str        # e.g. "ODbL (OpenStreetMap)"
    terms_status: str   # "permitted"
    regions: list[str]  # ["*"] or ISO codes

@dataclass
class AdapterQuery:
    area: dict           # {"city": "...", "region": "...", "bbox": [...]}
    categories: list[str]  # taxonomy keys (NOT source-specific)
    limit: int
    extra: dict          # adapter-specific knobs

@dataclass
class NormalizedLead:
    # canonical business record every adapter maps INTO; the core never sees source payloads
    business_name: str
    category_keys: list[str]
    address: dict        # line1, city, region, postal_code, country, lat, lon
    phone: str
    public_email: str
    website_url: str
    opening_hours: str
    attributes: dict     # open_7_days, franchise_status, number_of_locations, ...
    source_key: str
    source_url: str
    source_license: str
    raw_ref: str         # opaque id back to source record (audit)

class LeadSourceAdapter(Protocol):
    meta: SourceMeta
    def discover(self, query: AdapterQuery) -> Iterable[dict]: ...      # raw records
    def normalize(self, raw: dict) -> NormalizedLead | None: ...        # -> canonical
    def attribution(self) -> str: ...                                   # license/attribution text
```

- **OSM adapter (`osm.py`):** `discover` queries Overpass for `area + category tags`
  (taxonomy keys mapped to OSM tags via `CategoryMapping`); `normalize` maps OSM tags →
  `NormalizedLead`; `attribution` returns ODbL/OpenStreetMap text. Polite (existing rate
  limiting), no key required.
- **urlscan fingerprint adapter (`urlscan_fingerprint.py`):** wraps the existing engine —
  `discover` by fingerprint → hosts; `normalize` host → `NormalizedLead` (website-centric).
  Demonstrates the interface with a second, completely different source.
- The **ingestion pipeline** is the only consumer of adapters. The marketplace core consumes
  stored `Lead` rows and never imports an adapter.

---

## 5. Ingestion pipeline (`ingestion/pipeline.py`)

`discover (adapter) → normalize (adapter) → dedup → enrich (website/tech) → score (profile) →
compliance check (opt-out/suppression/lawful basis) → store Lead + LeadSource + AuditLog`.

- **Dedup:** by website domain, then phone, then (name similarity + geo proximity). Records
  duplicate confidence; merges into existing Lead when high-confidence.
- **Enrich:** `enrich/website.py` checks reachability + runs the tech fingerprint to populate
  digital-presence + intent signals (online ordering / booking / payment detected, ssl, etc.).
- **Score:** the recipe/ingestion specifies a `ScoringProfile` key; the scorer attaches
  sub-scores + total + explanation.
- **Comply:** drop/flag if opted-out or globally suppressed; stamp lawful_basis, license,
  retention.
- Admin triggers ingestion (`IngestionJob`); runs as a background task; progress visible in
  admin. (Reuses the existing async/job pattern.)

---

## 6. Scoring (profile-agnostic core + pluggable profiles)

```python
# scoring/engine.py
def score(lead, profile) -> ScoreResult:  # ScoreResult{subscores: dict, total: int, explanation: str}
    base = generic_subscores(lead)   # contactability, freshness, confidence, compliance, completeness
    return profile.combine(lead, base)
```

- **Generic sub-scores (core, vertical-free):** contactability (which contact fields present +
  verified), freshness (date_last_verified), confidence (source_confidence + completeness),
  compliance (opt-out/suppression clear).
- **`ScoringProfile` (profiles/base.py):** `fit(lead)`, `intent(lead)`, and `combine(lead, base)
  -> ScoreResult` with weights and a human explanation. Vertical-specific signals live here.
- **`utility_energy.py`:** adds `energy_usage_likelihood` (category heuristic + long-hours /
  7-day / multi-location / independent modifiers), weights fit+intent+contactability+freshness,
  and emits explanations like *"87 — independent restaurant, open 7 days, public phone, verified
  5 days ago, high energy-usage category, matches target city."* This file is the ONLY place
  `energy`/`utility` strings live.

---

## 7. Marketplace core (masking, recipes, purchasing) — vertical-free

- **LeadRecipe** = buyer's saved search: `filters_json` (categories[], location, contact
  requirements, freshness window, min score, exclusions) + `scoring_profile_key`. `recipes.py`
  compiles filters → a SQL query over the `Lead` inventory.
- **Estimate** (`marketplace.py`): matching count + score/freshness distribution + N masked
  sample previews + per-lead price (credits).
- **Masking** (`masking.py`, server-enforced):
  - *Preview projection* returns ONLY: category, city/region, score + sub-scores, booleans for
    which contact fields exist, reason-for-match, price, exclusivity, source type, freshness.
    Never name/phone/email/website/address.
  - *Unlock projection* (full record) is returned ONLY when a `PurchasedLead` exists for
    `(buyer, lead)`. Enforced at the serializer + route layer; no endpoint returns full contact
    without an ownership check.
- **Purchasing** (`purchasing.py`): credit ledger (`CreditTransaction`), unlock = check credits
  → check not-already-owned → check not suppressed/opted-out → create `PurchasedLead` + debit +
  audit. Re-buy of an owned lead is blocked (returns the existing purchase). Exclusivity schema
  present; slice-one default is non-exclusive.
- **Export** (`export.py`): CSV of the buyer's purchased leads (chosen fields), reusing the
  existing exporter; every export writes an `AuditLog` row.

---

## 8. Compliance spine (day one)

- Every `Lead` stores: `source_key`, `source_name`, `source_url`, `source_license`,
  `lawful_basis`, `date_discovered`, `date_last_verified`, `opt_out_status`,
  `suppression_status`, `retention_expiry`.
- **Server-enforced masking** (see §7) — no full contact pre-purchase, period.
- **Opt-out** (`OptOutRequest`) + **suppression** (`SuppressionList`/`Entry`, buyer-scoped and
  global): excluded from search, preview, purchase, AND export (defense in depth).
- **Buyer compliance acknowledgement** required before first purchase.
- **Business-level data only** — no personal decision-maker fields in slice one.
- **Attribution** (license text) stored per lead and shown in UI + exports (ODbL/OSM).
- **AuditLog** on every unlock, export, and admin mutation (actor, action, entity, time).

---

## 9. Data model (slice-one subset of spec §33; SQLite now, Postgres-ready)

`User`(email, password_hash, role, buyer_account_id) ·
`BuyerAccount`(company_name, credits, compliance_ack_at) ·
`Lead`(canonical business record + sub-scores + total_score + source/compliance metadata +
marketplace fields times_sold/last_sold/exclusivity) ·
`LeadSource`(key, name, type, url, license, terms_status, regions, active) ·
`LeadCategory`(key, label, parent_id) + `CategoryMapping`(source_key, external_value,
category_id) ·
`LeadRecipe`(buyer_account_id, name, filters_json, scoring_profile_key) ·
`PurchasedLead`(buyer_account_id, lead_id, price_credits, status, notes_json; unique(buyer,lead)) ·
`CreditTransaction`(buyer_account_id, delta, reason, ref) ·
`SuppressionList` + `SuppressionEntry`(kind, value) ·
`OptOutRequest`(kind, value, applied) ·
`AuditLog`(actor_user_id, action, entity, entity_id, meta_json) ·
`IngestionJob`(adapter_key, query_json, status, counts_json).

---

## 10. UI (Jinja2 + Tailwind dashboard)

- **Auth:** register, login, logout.
- **Buyer:** Dashboard (credits widget, counts) · Lead Recipes (builder + saved) · Marketplace
  (search results as **masked lead cards**: category, city, score, contact-fields badges,
  reason, price, exclusivity, Preview/Unlock) · Purchased Leads (full detail drawer, status
  pipeline, CSV export) · Suppression (upload domains/phones/emails) · Billing (credit balance +
  ledger; admin-granted in slice one).
- **Admin:** Ingestion (pick adapter + area + categories → run job) · Leads · Sources ·
  Categories (taxonomy CRUD) · Opt-outs · Audit Log.
- Reuse the existing emerald/clean aesthetic; quality/verification/compliance/source badges on
  lead cards.

---

## 11. Explicitly deferred (named, not forgotten)

Stripe/real payments (credits are **admin-granted** for now), CRM integrations, recurring feeds
+ alerts, public API, team RBAC beyond buyer/admin, the exclusivity engine (schema present,
non-exclusive default), verification beyond reachable/format checks, map-polygon drawing,
multi-source dedup beyond domain/phone/name+geo, Companies House (optional; only if a key is
supplied), public marketing site, onboarding questionnaire.

---

## 12. Testing (TDD)

Adapter `normalize` mapping (OSM tags → NormalizedLead) · taxonomy CRUD · scoring profile output
+ explanation · **masking enforcement** (preview never leaks contact; unlock requires a
purchase) · credit ledger + re-buy guard + insufficient-credits block · suppression/opt-out
exclusion across search+purchase+export · audit logging · ingestion pipeline e2e with a **fake
adapter** (no network) · CSV export · **grep test: `app/core/` free of energy/utility/osm/overpass**.

---

## 13. Acceptance criteria (slice one)

1. Buyer registers, logs in, is gated by compliance acknowledgement before first purchase.
2. Buyer builds a Lead Recipe (categories from DB taxonomy, location, contact requirements,
   freshness, min score, exclusions, scoring profile).
3. Buyer sees an estimate (count + distributions) and **masked** previews — no full contact.
4. Buyer unlocks leads with credits; blocked on insufficient credits, already-owned, or
   suppressed/opted-out.
5. Buyer views full purchased lead (contact + source URL + license + verification date + score
   explanation), sets status, and exports CSV.
6. Buyer uploads a suppression list; suppressed/opted-out leads never appear or export.
7. Admin runs an Overpass ingestion that populates real inventory (category+location+contact),
   deduped, enriched, scored, with source/license metadata.
8. Every unlock/export/admin mutation is in the audit log.
9. **Source-agnostic proof:** a second adapter (urlscan fingerprint) exists alongside OSM with
   zero changes to `app/core/`; the grep over `app/core/` for energy/utility/osm/overpass is
   clean.
10. Clean, professional dashboard UI; runs locally with `py -3.11 -m uvicorn app.main:app`.

---

## 14. North star (full platform)

The full spec (40 sections: scoring engine, exclusivity marketplace, Stripe billing, CRM
integrations, recurring feeds, public API, compliance center, admin analytics, 8 roles, 40+
entities) remains the target. Slice one is built so each later phase is an **addition**
(new adapter, new scoring profile, new delivery channel, new role) rather than a rewrite.
