# Composer UI pass + Country-Agnostic Architecture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use `- [ ]`.

> 🛑 **HARD STOP after this plan + the US-expansion doc.** Do NOT ingest the US, add US options/campaigns,
> or pitch a next phase. The UK utilities demand test remains the next real gate. This makes the demo
> nicer to put in front of testers and removes UK-hardcoding so the US *can* slot in later — it does not
> launch the US. **Payments PARKED.**

**Goal:** (1) A proper composer UI/UX pass — multi-select city with "select all", clearly-visible selected
state on every multi-value control, searchable/scrollable long lists, design-system-consistent, pleasant;
data-driven + guided/advanced kept. (2) Remove UK-hardcoding so the architecture is country-agnostic:
configurable phone-validation region, first-class multi-value geo predicates (country/state/city),
ingestion that stamps country from the pull context.

**Architecture:** Phase 1 makes the engine country-agnostic (phone region from the lead's country;
`geo.*_any` list predicates; ingest country stamping). Phase 2 is a composer-template UI pass that
consumes the new multi-value geo predicate. No US data, no US campaign, no US UI — capability only.

**Tech Stack:** Python 3.11 (`.venv/Scripts/python`), FastAPI/SQLModel, Jinja + Tailwind (shipped design
system), `phonenumbers`, pytest. Browser verification via the running app on :8080.

## Global Constraints
- Interpreter `.venv/Scripts/python`; tests `.venv/Scripts/python -m pytest`. Bash for git; no `cd`. Do
  NOT commit `*.db`. Pilot server holds `leadvault.db` — do NOT `rm` it; suite uses a temp DB.
- **No US launch:** do NOT ingest US areas, seed US campaigns, or add US-specific UI options. Phase 1 is
  capability only. US remains "not built / not available" until the user decides from the separate doc.
- **No regression for the UK pilot:** existing GB leads must validate identically (region derived from
  `country="GB"` → "GB"); the default region stays "GB" so current behavior is unchanged. Existing stored
  `validation_json` is NOT recomputed by this change (only new ingests use the new path).
- **Data-driven, guided + advanced kept** (composer). Options from real inventory (coverage rollup /
  `_inventory_options`). Masking / quality gate / INV-Q1 / suppression / ODbL / grep-clean core all HOLD.
- **INV-Q1 unchanged:** the baseline hot-gate still applies everywhere; nothing here weakens it.
- **Browser-test the UI (Phase 2):** these usability bugs hide from a clean diff — verify in the running
  browser, not only the suite. TDD for backend; frequent commits.

**Grep-clean note:** geo/phone/ingest changes stay generic; no `us|united states|state-name` literals in
`app/core` beyond neutral field names. The word "GB" as a configurable DEFAULT constant is fine (it's a
default, not a hardcoding) but must be overridable.

---

## File Structure
```
app/quality/validators/phone.py      # already region-parameterized (keep)
app/quality/stamp.py                  # build_validation(..., region=None) -> derive region from country
app/ingestion/pipeline.py            # pass lead country as phone region; optional country stamping
app/targeting/predicates/geo.py       # + _GeoAny: geo.city_any / geo.region_any / geo.country_any (in:[list])
app/targeting/runtime.py              # register the new geo_any predicates
app/core/config.py (or existing)      # DEFAULT_PHONE_REGION = "GB" (configurable)
app/web/templates/composer.html       # UI pass: multi-select city + visible selected state + polish
tests/test_phone_region.py test_geo_any.py test_ingest_country.py
docs/superpowers/plans/2026-07-02-us-expansion.md   # separate doc (written after build)
```

---

## PHASE 1 — Country-agnostic architecture

### Task 1: Configurable phone-validation region (derive from country)

**Files:** Modify `app/quality/stamp.py`, `app/ingestion/pipeline.py`; add a `DEFAULT_PHONE_REGION`
constant (in the existing config module — grep for where other config constants live, e.g. `app/core/config.py`
or `app/quality/`); Test `tests/test_phone_region.py`.

**Interfaces — Produces:** `build_validation(fields, *, region=None, mx_lookup=None)` — if `region` is
None, derive it: `region = _region_for(fields.get("country",""))` where `_region_for(country)` returns
`country.strip().upper()` when that is a 2-letter code, else `DEFAULT_PHONE_REGION`. Pass `region` to
`validate_phone(phone, region=region)`. The ingest passes the lead's country in the `fields` dict.

- [ ] **Step 1: Failing test** (`tests/test_phone_region.py`)
```python
from app.quality.stamp import build_validation

def test_phone_region_derived_from_country():
    # A US number is INVALID when parsed as GB (today's behavior) ...
    gb = build_validation({"phone": "+1 415 555 2671", "country": "GB"})
    # ... but VALID when the country drives the region:
    us = build_validation({"phone": "+1 415 555 2671", "country": "US"})
    assert us["phone"]["valid"] is True
    assert us["phone"]["tier"] in ("validated", "present")  # match your tier vocabulary
    # A GB number still validates as GB (no regression):
    gbnum = build_validation({"phone": "020 7946 0018", "country": "GB"})
    assert gbnum["phone"]["valid"] is True
    # Unknown country falls back to the configurable default (GB), unchanged behavior:
    dflt = build_validation({"phone": "020 7946 0018", "country": ""})
    assert dflt["phone"]["valid"] is True
```
(Confirm the exact keys `validate_phone` returns — read `phone.py` — and assert against the REAL shape;
`+1 415 555 2671` is a valid US number, invalid as GB.)
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** `_region_for` + `DEFAULT_PHONE_REGION="GB"` (configurable via env if the app
  has a config pattern — else a module constant), thread `region` through `build_validation` → `validate_phone`.
  In `pipeline.py` where `build_validation({...})` is called, include `"country": addr.get("country","")`
  (or the lead's country) in the fields dict so region derives correctly.
- [ ] **Step 4: Run — PASS + full suite** (existing GB validation unaffected — stored `validation_json`
  is not recomputed; new path derives GB for GB leads).
- [ ] **Step 5: Commit** `feat(quality): phone-validation region derived from lead country (configurable default, was hard GB)`

### Task 2: First-class multi-value geo predicates

**Files:** Modify `app/targeting/predicates/geo.py`, `app/targeting/runtime.py`; Test `tests/test_geo_any.py`.

**Interfaces — Produces:** `_GeoAny(key, path, column, label)` with `params_schema={"in":"list[string]"}`,
`group="geographic"`. `matches(view, params)`: read the path; if MISSING/empty → `None` (tri-state); else
return True if the value matches ANY entry in `params["in"]` (case-insensitive substring), False otherwise;
empty `in` list → `None`. `sql_pushdown`: OR of `column.ilike(%v%)` for each v (None if empty). Register
`GEO_CITY_ANY=_GeoAny("geo.city_any","city",Lead.city,"City is any of")`,
`GEO_REGION_ANY=_GeoAny("geo.region_any","region",Lead.region,"Region/State is any of")`,
`GEO_COUNTRY_ANY=_GeoAny("geo.country_any","country",Lead.country,"Country is any of")`.

- [ ] **Step 1: Failing test** (`tests/test_geo_any.py`)
```python
import json
from sqlmodel import Session
from app.core.db import init_db, Lead, _now
from app.core.targeting import registry
from app.targeting.runtime import register_targeting_runtime
from app.core.targeting.view import lead_view

def _mk(city): return Lead(business_name="B", city=city, country="GB", phone="1", score_total=50,
                           category_keys_json="[]", date_last_verified=_now())

def test_geo_city_any_matches_any_of_list():
    registry.clear(); register_targeting_runtime()
    p = registry.get("geo.city_any")
    assert p.matches(lead_view(_mk("Oxford")), {"in": ["Oxford", "Norwich"]}) is True
    assert p.matches(lead_view(_mk("Bristol")), {"in": ["Oxford", "Norwich"]}) is False
    assert p.matches(lead_view(_mk("")), {"in": ["Oxford"]}) is None          # tri-state absent
    assert p.matches(lead_view(_mk("Oxford")), {"in": []}) is None            # empty selection
```
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** `_GeoAny` + register the three. (Keep `_GeoEq` singles for back-compat — campaign
  templates still emit `geo.city`/`geo.country`.)
- [ ] **Step 4: Run — PASS + full suite.** Then recompute coverage note: the new predicates' `reads` are
  `city`/`region`/`country` (already tracked) so they appear available where those are populated.
- [ ] **Step 5: Commit** `feat(targeting): first-class multi-value geo predicates (geo.city_any/region_any/country_any)`

### Task 3: Ingest stamps country from pull context

**Files:** Modify `app/ingestion/pipeline.py` (+ the `AdapterQuery` dataclass wherever it's defined — grep);
Test `tests/test_ingest_country.py`.

**Interfaces — Produces:** the ingest accepts an optional country for the pull (e.g. `AdapterQuery` gains
`country: str = ""`, or `ingest(..., country="")`); when set, the stamped `Lead.country` uses it as a
fallback when the OSM `addr:country` tag is absent (so a "Austin, US" pull stamps `US`, an "Oxford, GB"
pull stamps `GB`) — OSM tag wins when present, the pull country fills the gap. Do NOT pull any US area;
this is capability only.

- [ ] **Step 1: Failing test** (`tests/test_ingest_country.py`): drive `ingest` (or the row-building
  helper) with a fake adapter yielding a node with NO `addr:country`, and a pull country="GB" → the
  created `Lead.country == "GB"`. A node WITH `addr:country="US"` keeps "US" regardless of pull country.
  (Follow the existing ingestion test pattern — read `tests/test_ingestion.py`.)
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** the fallback (`country = addr.get("country") or query.country or ""`).
- [ ] **Step 4: Run — PASS + full suite** (existing ingest tests unaffected — default country="" keeps
  current behavior).
- [ ] **Step 5: Commit** `feat(ingestion): stamp country from pull context when OSM tag absent (country-agnostic; no US pull)`

---

## PHASE 2 — Composer UI pass

### Task 4: Multi-select city + visible selected state + control polish (BROWSER-TESTED)

**Files:** Modify `app/web/templates/composer.html` (+ if needed the composer route to pass any extra data
it already has). Verify in the browser on :8080.

**Consumes:** `cities` (real inventory list, already passed), `cat_options`, `options` (available/unavailable
predicates), `geo.city_any` (Task 2). **Produces:** a polished composer where every multi-value control is
a clear multi-select.

Requirements (match the shipped design system — `components.html` macros, brand-600 accent, rounded-xl,
tokens):
- [ ] **Step 1: City → MULTI-SELECT (guided).** Replace the single `#guidedCity` text input with a
  multi-select chip control (same interaction model as the business-types chips): a searchable input over
  the real `cities` list + a **"Select all"** action + a **"Clear"** action; chosen cities render as
  removable chips with a clearly-visible selected state. `buildComposition()` emits
  `geo.city_any {in: [<cities>]}` when ≥1 city is chosen (a single city → `{in:[one]}`; none → no city
  node). Update `_loadCompositionPreset` so a campaign/segment `geo.city {value:X}` OR
  `geo.city_any {in:[...]}` both hydrate the multi-select (add the value(s) as selected chips).
- [ ] **Step 2: Business types — VISIBLE selected state.** The suggestion list must show which options are
  SELECTED (checkmark or filled/highlighted state on the suggestion, not only a separate chip); selected
  chips stay visible and removable. Make the suggestion list **searchable** (filter as you type) and
  **scrollable** when long (cap height, scroll) — it is data-driven from `cat_options`.
- [ ] **Step 3: Audit EVERY control.** Walk each control (guided: city, business types, quality, freshness;
  advanced: every predicate row incl. the greyed ones): anything that should allow multiple values does
  (city/region/category via `*_any` / list params); the selected state is always visible; long option
  lists are searchable/scrollable; spacing/labels/hover/focus are design-system-consistent; nothing feels
  capped or truncated. Fix anything awkward. Keep guided-vs-advanced and the live estimate + gated-notice
  rows intact.
- [ ] **Step 4: BROWSER VERIFICATION (required — do not skip).** With the app running on :8080 (restart it
  if you changed routes: kill the listener on 8080, relaunch `uvicorn app.leadvault:app`), log in
  (`buyer@demo.local`/`buyer12345`) and drive the composer via Playwright or a scripted check:
  (a) select **Oxford + Norwich** in the city multi-select → the composition contains
  `geo.city_any {in:["Oxford","Norwich"]}` and the estimate count ≈ Oxford+Norwich (>34); (b) "Select all"
  selects every inventory city and the count rises accordingly; (c) picking business types shows a visible
  selected state and filters the count; (d) applying the Utilities campaign still loads + estimates
  (regression check). Capture what you verified. If Playwright isn't available to you, curl the estimate
  endpoint with the composed JSON to prove the counts, and inspect the rendered HTML for the selected-state
  markup.
- [ ] **Step 5: Parse-check templates + full suite green. Commit**
  `feat(composer): multi-select city (+ select all) & visible selected-state on all multi-value controls; searchable/scrollable lists`

---

### Task 5: Whole-branch review + browser sign-off
- [ ] Full suite + template parse + `grep -rinE "campaign|utilit|restructur|mca|lender|amount_owed|vertical" app/core/` empty.
- [ ] Dispatch a whole-branch reviewer (most-capable model) over the branch diff: confirm INV-Q1 unchanged,
  no US data/options introduced, phone-region default preserved (no UK-pilot regression), geo_any tri-state
  correct, grep-clean core, composer still masked/gated/honest.
- [ ] Controller browser sign-off of the multi-select city + visible selected state + campaign regression.
- [ ] Fix Critical/Important findings (one fix subagent, complete list). Record minors.

## Self-Review
**Coverage:** multi-select city + select-all (T2+T4), visible selected state on business types + all controls
(T4), searchable/scrollable (T4), data-driven + guided/advanced kept (T4), design-system (T4); configurable
phone region (T1), first-class multi-value geo incl. state/country (T2), ingest country stamping / US-area
capability (T3). US NOT built (constraint enforced across all tasks).
**Deferred to the US doc (NOT built):** US ingest, US OSM yield measurement, a US campaign + its quality
profile, US compliance review. Written as `docs/superpowers/plans/2026-07-02-us-expansion.md` — decision
material, not a build.
**Placeholder scan:** backend tasks carry full code; T4 is a browser-verified UI contract against the shipped
design system. **Type consistency:** `geo.city_any` params `{in:[...]}` matches `category.any`'s list shape
and the evaluator; `build_validation(..., region=...)` matches `validate_phone(phone, region=...)`.

**🛑 After this plan + the US doc: HARD STOP. No US build, no phase pitch. UK utilities demand test is the
next gate — the user's call. Payments parked.**
