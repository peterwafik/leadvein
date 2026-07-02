# Waterfall Enrichment Capability — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use `- [ ]`.

> 🛑 **STOP after this plan for user review.** Deliver the capability + the two first adapters + the keys
> report (`2026-07-02-data-providers-keys.md`), then STOP — the user gets the API keys worth it. Do NOT
> ingest US business data, do NOT enable US outreach, do NOT scrape or wire ToS-restricted providers
> (Google Places / Yelp / LinkedIn). **Payments PARKED. The UK utilities demand test remains the real gate.**

**Goal:** Extend the adapter layer to plug in external business-data providers via **waterfall
enrichment** — OSM stays the free base; source adapters fill missing businesses; enrichment adapters fill
missing/unverified **role-based** business contacts. Per-field provenance + license, per-source rate/credit
budgeting, feature-flagged (disabled with no key, like Stripe), honesty spine unchanged. Wire the first
two adapters (**Companies House** UK source; **Hunter.io** email enrichment). Flag US leads for the
DNC/TCPA gate and hold them from sale.

**Architecture:** New `EnrichmentAdapter` protocol beside the existing `LeadSourceAdapter`. A feature-flag
registry (enabled iff the adapter's `key_env` is set). A generic `SourceBudget` (rate + free-tier cap) +
per-field `field_provenance_json` on `Lead` (both generic — no provider strings in core). A `waterfall`
runner fills gaps only (never overwrites better data), stamps provenance, respects budget/rate. Concrete
provider code + all provider strings live under `app/adapters/providers/` — **never `app/core`**.

**Tech Stack:** Python 3.11 (`.venv/Scripts/python`), FastAPI/SQLModel, `requests` (HTTP, mocked in
tests), pytest. Reuses `SourceMeta`/`AdapterQuery`/`NormalizedLead`/adapter `registry`, the quality gate,
masking, serve_filters, `audit`, INV-2 role-email allowlist.

## Global Constraints
- Interpreter `.venv/Scripts/python`; tests `.venv/Scripts/python -m pytest`. Bash for git; no `cd`. Do NOT
  commit `*.db`. Pilot server holds `leadvault.db` — do NOT `rm` it; suite uses a temp DB.
- **No live API calls in the suite.** Every adapter takes an injectable HTTP client / is mockable offline
  (the Stripe-mock pattern). Tests must pass with zero network + zero keys.
- **Feature-flag / disabled-mode:** an adapter is ENABLED iff `meta.key_env == "" or os.getenv(meta.key_env)`.
  With no keys, all external adapters are disabled and the app runs on OSM alone. Never hardcode a key;
  never read a key from anywhere but env.
- **Honesty spine (unchanged):** masking, quality gate (**INV-Q1**), suppression/opt-out, ODbL + per-field
  license attribution, retention, audit ALL apply to externally-sourced leads exactly as to OSM leads. An
  enriched contact is "hot" only after it clears validation. **No fabrication** — adapters return real API
  values or nothing; no inferred/placeholder contacts.
- **People-data guard:** enrichment keeps ONLY role-based business emails (INV-2 allowlist) + published
  business phones; personal emails/named-person contacts are DISCARDED. Companies House ingests **company
  fields only — never officer/director personal data**.
- **Waterfall, not overwrite:** only fill fields that are missing or unverified; never overwrite a
  higher-tier/verified value with a lower one.
- **US gate:** US-region leads get a compliance flag "requires DNC-scrub + TCPA-consent gate before
  outreach" and are **held from sale** (a serve-filter blocks them at preview/unlock) until that gate is
  built. Do NOT ingest US businesses in this plan.
- **INV — grep-clean core (strict):**
  `grep -rinE "hunter|apollo|companies.?house|foursquare|people.?data|linkedin|google.?places|yelp|tcpa|dnc|provider.?key" app/core/` → empty. Provider names + terms + keys live only under `app/adapters/` + `app/compliance/` + `.env`. Core sees only generic `SourceBudget`, `field_provenance_json`, and neutral serve-filters.
- TDD; frequent commits; adapters mockable/offline.

## File Structure
```
app/adapters/base.py            # + EnrichmentAdapter protocol, FieldContribution; SourceMeta += key_env/free_tier/rate_limit
app/adapters/registry.py        # + enabled(adapter), list_status(session) (flag + budget)
app/adapters/budget.py          # SourceBudget logic: record_use / remaining / would_exceed (model in core/db, generic)
app/adapters/waterfall.py       # run_enrichment(session, lead, adapters) — fill gaps, stamp provenance, respect budget
app/adapters/providers/companies_house.py   # UK source (LEADVAULT_COMPANIES_HOUSE_KEY) — company fields only
app/adapters/providers/hunter.py            # email enrichment (LEADVAULT_HUNTER_KEY) — role-emails only, budgeted
app/core/db.py                  # + SourceBudget (lv_source_budget) + Lead.field_provenance_json  (GENERIC)
app/compliance/outreach_gate.py # country->compliance-region; US-hold serve-filter (no provider strings)
app/web/routes_admin.py + templates/admin_sources.html   # connected sources + remaining free credits
tests/test_enrichment_registry.py test_source_budget.py test_waterfall.py test_companies_house.py test_hunter.py test_us_hold.py test_enrichment_grepclean.py
```

---

### Task 1: EnrichmentAdapter protocol + feature-flag registry
**Files:** Modify `app/adapters/base.py`, `app/adapters/registry.py`; Test `tests/test_enrichment_registry.py`.
**Produces:** `SourceMeta` gains `key_env: str = ""`, `free_tier: dict = field(default_factory=dict)`,
`rate_limit: dict = field(default_factory=dict)` (all defaulted → OSM/urlscan unaffected).
`FieldContribution` dataclass `{field:str, value, license:str, confidence:float=1.0}`. `EnrichmentAdapter`
Protocol: `meta: SourceMeta`; `enrich(self, view: dict) -> list[FieldContribution]`. Registry:
`enabled(adapter) -> bool` (`meta.key_env=="" or bool(os.getenv(meta.key_env))`); `list_status(session)`
→ `[{key,name,type,enabled,terms_status,free_tier,used,remaining}]`.
- [ ] **Step 1: Failing test** — a fake enrichment adapter with `meta.key_env="LEADVAULT_FAKE_KEY"` is
  `enabled()==False` when the env var is unset, `True` when set (monkeypatch env); a keyless adapter
  (`key_env==""`) is always enabled; a `terms_status="restricted"` adapter reports restricted in status.
- [ ] **Step 2: Run — FAIL.** **Step 3: Implement.** **Step 4: PASS + full suite.**
- [ ] **Step 5: Commit** `feat(adapters): EnrichmentAdapter protocol + feature-flag registry (disabled without key)`

### Task 2: SourceBudget + per-field provenance
**Files:** Modify `app/core/db.py` (generic `SourceBudget` + `Lead.field_provenance_json`); Create
`app/adapters/budget.py`; Test `tests/test_source_budget.py`.
**Produces:** `SourceBudget(lv_source_budget: id, source_key indexed, used int, cap int, window_start,
updated_at)`. `budget.record_use(session, source_key, cap, n=1) -> int` (returns used); `remaining(session,
source_key, cap) -> int`; `would_exceed(session, source_key, cap, n=1) -> bool`. `Lead.field_provenance_json`
= JSON `{field: {"source":str,"license":str,"at":str}}` default `"{}"`; helper `stamp_provenance(lead,
field, source, license)`.
- [ ] **Step 1: Failing test** — record_use accumulates; would_exceed True at cap; remaining decrements;
  stamp_provenance writes `{field:{source,license,at}}`.
- [ ] Steps 2–4 (fail→implement→pass + suite). **Step 5: Commit** `feat(adapters): per-source budget + per-field provenance (generic core)`

### Task 3: Waterfall enrichment runner
**Files:** Create `app/adapters/waterfall.py`; Test `tests/test_waterfall.py`.
**Produces:** `run_enrichment(session, lead, adapters, *, http=None) -> dict` (counts). For each ENABLED
enrichment adapter, in order: skip if `would_exceed` its free cap; call `adapter.enrich(lead_view(lead))`;
for each `FieldContribution` whose target field on the lead is **missing or unverified**, apply it, stamp
provenance + license, `record_use`, and re-run validation on the changed field. NEVER overwrite a
verified/higher-tier value. Returns per-source fill counts. (Uses `lead_view`, the quality validators,
`stamp_provenance`, budget.) The gate/masking/suppression are unchanged and still applied downstream at
serve time.
- [ ] **Step 1: Failing test** — with two fake enrichment adapters (one over budget, one returning a
  role-email FieldContribution for a lead missing `public_email`): the over-budget one is skipped; the
  other fills `public_email`, stamps provenance, records use; a lead that ALREADY has a verified phone is
  NOT overwritten by a fake lower-tier phone contribution.
- [ ] Steps 2–4. **Step 5: Commit** `feat(adapters): waterfall enrichment runner (fill-gaps only, provenance + budget, no overwrite)`

### Task 4: Companies House source adapter (UK, mocked)
**Files:** Create `app/adapters/providers/companies_house.py`; Test `tests/test_companies_house.py`.
**Produces:** `CompaniesHouseAdapter` (`LeadSourceAdapter`) — `meta=SourceMeta(key="companies_house",
name="Companies House", type="registry", url=..., license="Companies House / Open Government Licence v3.0",
terms_status="permitted", regions=["GB"], key_env="LEADVAULT_COMPANIES_HOUSE_KEY", rate_limit={"per":300,
"seconds":300})`. `discover(query)` calls the CH search API (`https://api.company-information.service.gov.uk`,
HTTP Basic auth with the key as username) via an **injectable http client** (default `requests`, mocked in
tests); `normalize(raw)` → `NormalizedLead` with **company fields only**: business_name, address (registered
office), category_keys from SIC codes (map a few common SIC→category), attributes `{incorporation_date,
company_status, sic_codes}`, source_key/license set. **NO phone/email (CH doesn't provide them). NO officer
personal data.**
- [ ] **Step 1: Failing test** — feed a canned CH JSON response through a fake http client → `discover`
  yields items, `normalize` produces a NormalizedLead with the company name/address/SIC-category + the
  attributes, no phone/email, correct license; officers are ignored.
- [ ] Steps 2–4 (no live call). **Step 5: Commit** `feat(adapters): Companies House UK source adapter (company fields only; OGL; mocked)`

### Task 5: Hunter.io email-enrichment adapter (role-emails only, budgeted, mocked)
**Files:** Create `app/adapters/providers/hunter.py`; Test `tests/test_hunter.py`.
**Produces:** `HunterAdapter` (`EnrichmentAdapter`) — `meta=SourceMeta(key="hunter", name="Hunter.io",
type="email_enrichment", url=..., license="Hunter.io API Terms", terms_status="permitted", regions=["*"],
key_env="LEADVAULT_HUNTER_KEY", free_tier={"cap":25,"window":"month"})`. `enrich(view)`: if the lead has a
website domain and is missing a role-email, call Hunter domain-search (injectable http, mocked); **filter
returned emails to role-based only** using the existing INV-2 role-email allowlist; return at most one
`FieldContribution(field="public_email", value=<role_email>, license="Hunter.io API Terms")`. Personal
emails are DISCARDED. No result → `[]`.
- [ ] **Step 1: Failing test** — a canned Hunter response containing both `john.smith@acme.com` (personal)
  and `sales@acme.com` (role): `enrich` returns ONLY the role email as a FieldContribution; a response with
  only personal emails returns `[]`; no domain → `[]`.
- [ ] Steps 2–4 (no live call). **Step 5: Commit** `feat(adapters): Hunter.io email enrichment (role-emails only, INV-2 allowlist; free-tier capped; mocked)`

### Task 6: Admin connected-sources view + US outreach hold-gate
**Files:** Create `app/compliance/outreach_gate.py`; Modify `app/web/routes_admin.py`,
`app/web/templates/admin_sources.html`; register the serve-filter at startup (`app/leadvault.py`); Test
`tests/test_us_hold.py`.
**Produces:** `outreach_gate.compliance_region(country) -> str` (e.g. "US" for US); `us_outreach_hold_filter(
session, buyer_account_id, lead, ctx=None) -> bool` returning False (held) for a lead whose
`compliance_region` is US and lacks a cleared DNC/TCPA flag — registered into the serve_filters chain so US
leads are blocked at preview/unlock/search (INV-Q1-style). Admin `/admin/sources` shows `list_status()`:
each source's enabled/disabled, terms_status, free cap, used, remaining — plus a clear "US outreach: held
pending DNC/TCPA gate" banner.
- [ ] **Step 1: Failing test** — a lead with country="US" is absent from a composer estimate / raises on
  unlock (held) while a GB lead is served normally; `compliance_region("US")=="US"`, `("GB")=="GB"`.
- [ ] Steps 2–4. **Step 5: Commit** `feat(compliance): US outreach hold-gate (DNC/TCPA) + admin connected-sources & remaining-credits view`

### Task 7: INV tests for external leads + grep-clean + whole-branch review prep
**Files:** Test `tests/test_enrichment_invariants.py`, `tests/test_enrichment_grepclean.py`.
- [ ] **INV-Q1 for external leads:** a lead sourced/enriched by a (fake) provider still must clear the
  quality gate to surface; a non-hot enriched lead is absent from search/estimate and cannot be unlocked.
- [ ] **Spine parity:** masking hides the enriched contact on cards; suppression/opt-out blocks an
  externally-sourced lead; per-field provenance/license is present on an enriched field; ODbL still shown
  for OSM-origin fields.
- [ ] **grep-clean core:** `grep -rinE "hunter|apollo|companies|foursquare|people.?data|linkedin|google.?places|yelp|tcpa|dnc"` on `app/core/**/*.py` → empty (assert in the test).
- [ ] Full suite + parse + grep green. **Commit** `feat(adapters): INV-Q1 + spine + grep-clean tests for externally-sourced leads`

## Self-Review
**Coverage:** pluggable source + enrichment adapters via waterfall (T1/T3); per-field provenance + license
(T2); feature-flag disabled-without-key (T1); per-source rate + free-tier budget + admin remaining (T2/T6);
country-agnostic (reuses the geo_any + country work); Companies House source (T4) + Hunter enrichment (T5)
wired end-to-end mocked; people-data guard (role-emails only, no CH officers) (T5/T4); US DNC/TCPA hold-gate
+ no US ingest (T6); honesty spine + INV-Q1 + grep-clean for external leads (T7). The keys/coverage/ToS
honesty is delivered in `2026-07-02-data-providers-keys.md`.
**Deferred (NOT built; documented in the keys report):** Foursquare / PDL / Apollo adapters (framework is
ready — each is a small adapter once its key + ToS are confirmed); a real DNC-scrub data source (the US gate
holds US leads until it exists); whole-country bulk ingestion runs (operator action). No ToS-restricted
provider is wired.
**Placeholder scan:** backend + tests carry full code / canned-response contracts; adapters are mocked
offline. **Type consistency:** `FieldContribution{field,value,license}` flows waterfall→provenance;
`SourceMeta.key_env/free_tier` drive registry+budget; serve-filter signature matches the `ctx=None` chain.

**🛑 After this plan: STOP for user review. User gets the keys worth it. No US ingest, no ToS-restricted
providers, no phase pitch. UK utilities demand test is the gate. Payments parked.**
