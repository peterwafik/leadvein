# LeadVault — Campaign Layer (Design Spec)

**Date:** 2026-07-01
**Status:** 🔒 **LOCKED (approved 2026-07-01).** Design is final; no further changes without an explicit
re-open. SPEC ONLY — no code until the build gate below is met. **Do NOT build yet.**
**Reconciliation note (2026-07-01, not a re-open):** in code the Segment provenance field is named
**`origin_key`**, not `source_campaign_key` — renamed during the Targeting engine build so the string
"campaign" stays out of `app/core` (grep-clean-core, INV-9). Every `source_campaign_key` reference below
maps to `origin_key`; the Campaign layer sets it to the campaign key. Purely a name change; behaviour
and intent are unchanged.
**Extends:** `2026-06-30-targeting-segmentation-design-v2.md` (Targeting v2). This is a higher-level
layer *on top of* v2 — it reuses v2's predicate composition + Segment + scoring machinery verbatim and
adds no parallel engine.
**Build order (unchanged):** pilot-readiness checklist green → **Targeting v2 built** → **THEN** Campaign
layer. Not to be interleaved with pilot hardening.
**Scope:** a company describes a campaign; the tool compiles it into a saved Segment (predicate
composition) + scoring profile that selects compatible leads **across categories**, not by a single
taxonomy bucket. A "Campaign" selector in the buyer UI auto-populates the Recipe/Segment with the
campaign's composition (buyer can still tweak).

---

## 1. Goal & relationship to Targeting v2

A **Campaign** is a higher-level, admin-defined **preset**. Selecting one **compiles** to exactly the
artifacts the buyer could have built by hand in the Targeting composer:
1. a **predicate composition** (v2 §5) → seeds a **Segment** (v2 §5), and
2. a **scoring profile** (the existing pluggable scorer) → ranks the matched leads.

Everything from Targeting v2 applies **unchanged**: tri-state null-handling (INV-1: absent ⇒ unknown ⇒
non-match, including under negation), the two-stage SQL+Python evaluator (v2 §7), masking, credit-unlock,
suppression/opt-out, retention, and audit. The Campaign layer produces a composition; the compliance
spine and evaluator do the rest exactly as today. **No parallel engine.**

Campaigns select **regardless of category**: they compose cross-category attributes (firmographic,
geographic, contactability, web-presence), and never pin a single taxonomy bucket unless the campaign
explicitly asks for one.

---

## 2. A Campaign is DATA (admin-defined), not code

A campaign is a DB row (like the taxonomy), authored by an admin — **adding a campaign = adding data
(+ optionally a scoring profile), never touching `app/core`.**

`Campaign` model — **lives OUTSIDE `app/core`** (in `app/campaigns/models.py`) so that even the word
"campaign" stays out of the marketplace core; the core only ever sees the compiled composition/Segment:

```
Campaign (lv_campaign):
  id, key (unique), name, description, active,
  composition_template_json,   # REQUIRED predicates (AND) + EXCLUSIONS (negated) as a v2 composition
                               #   template, with named parameter placeholders (e.g. {area})
  preferred_json,              # [{predicate, params, boost}] — score boosts, NOT filters
  scoring_profile_key,         # the pluggable profile used to rank (e.g. "utility_energy",
                               #   or the generic "campaign_weighted" driven by preferred_json)
  gated_signals_json,          # [attribute paths this campaign WOULD use but that require a gated,
                               #   licensed Signal Acquisition source] — for the "not available" UI notice
  param_schema_json,           # buyer-fillable params (e.g. area = region/city) with types/help
  created_at
```

- **required** predicates → the AND branch of the compiled composition (hard filters).
- **preferred** predicates → **score boosts** applied by the scoring profile when the predicate is
  `True` (tri-state: `unknown`/`False` ⇒ **no boost, never a fabricated penalty**). They rank, they
  never exclude.
- **exclusions** → negated leaves (thin sugar over `negate`, v2 §5). The always-on
  suppressed/opted-out exclusions stay server-enforced and are NOT part of the composition.
- **scoring_profile** → an existing registered profile, or the generic **`campaign_weighted`** profile
  that reads `preferred_json` and applies honest tri-state boosts (so the common case needs **no new
  profile code** — the campaign stays pure data).

**Grep-clean (stricter than v2, per direction):** `grep -rinE "campaign|vertical-name|financial-term"
app/core/` → empty. The `Campaign` model, `compile_campaign`, CRUD, and the seeded campaign rows all
live under `app/campaigns/`; vertical/financial strings live in `app/campaigns/seed.py`, the scoring
profiles (`app/scoring/profiles/`), and the deferred gated source — **never in `app/core`**. Buyer/admin
tokens travel as **data** in `composition_template_json` / `preferred_json` / `gated_signals_json`.

---

## 3. Compilation

`app/campaigns/compile.py` (generic transform — reads a Campaign row, emits v2 artifacts; no
per-campaign strings):

```python
compile_campaign(campaign, buyer_params) -> CompiledCampaign
CompiledCampaign = {
  "composition": <v2 composition>,        # AND(required, params merged) + negated exclusions
  "scoring_profile_key": <str>,           # campaign.scoring_profile_key
  "preferred": <list>,                    # passed to the scoring profile as boosts
  "gated_notices": [ {path, reason} ],    # gated_signals with no licensed source -> UI "not available"
}
```

- The output `composition` is an ordinary v2 composition → it seeds a **Segment** the buyer can tweak,
  re-estimate, save, and use to search — through the exact v2 machinery (two-stage evaluator, tri-state,
  masking, credit-unlock, suppression/opt-out, audit).
- `gated_notices` lists any `gated_signals` for which **no licensed source is registered** → the UI
  renders "not available — requires licensed source" (see §7). Gated predicates are **never** placed in
  the read-time composition.
- `Segment` gains an optional `source_campaign_key` (provenance/audit); otherwise the Segment model is
  unchanged from v2.

---

## 4. UI — the Campaign selector

- A **"Campaign"** dropdown (active campaigns) sits above the Recipe/Segment composer.
- Selecting a campaign → server compiles it (with the buyer's `param_schema` inputs, e.g. area) →
  **auto-populates the composer** with the resulting composition and sets the scoring profile. The
  buyer can then **tweak** any predicate, add/remove filters, and save as their own Segment.
- The composer's data-driven availability (v2 §6 rollup) still applies: required/preferred predicates
  whose signals aren't populated in current inventory show disabled with the "populated on N%" figure;
  `gated_notices` render as **"not available — requires licensed source"** (distinct from "no
  inventory coverage yet").
- Live **estimate** (count + score/freshness histograms + masked samples) updates as the buyer tweaks —
  debounced/cached/capped per v2 §7.

---

## 5. Audit

Extend the audit log (v2 §7/§11 unchanged otherwise) with campaign events:
- **campaign.create/update** (admin authored/edited a campaign),
- **campaign.select** (buyer selected a campaign → composer populated; records campaign key + compiled
  composition hash),
- **campaign.search** (a Segment derived from a campaign drove a search).

"Who targeted what," on top of the existing unlock/export audit.

---

## 6. SEEDED CAMPAIGN 1 — "Utilities (UK)" (end-to-end, fully lawful today)

**Intent:** all reachable UK businesses in a chosen area with a usable business contact —
**across all categories**, ranked by energy-usage fit.

**Compiles to (v2 composition):**
```
op: AND, nodes: [
  { predicate: "geo.country",             params: {value: "GB"} },            # fixed
  { predicate: "geo.area",                params: {region|city: "{area}"} },  # buyer param
  { predicate: "contactability.has_business_contact", params: {} }            # usable contact
]
```
- `contactability.has_business_contact` = has `phone` **OR** a role-based `public_email` (role-prefix
  allowlist, INV-2). "Reachable/usable contact" ⇒ contactable by a published business channel. NO
  category filter (cross-category by design).
- **Exclusions:** `exclude.already_purchased` (default on, tweakable). Suppressed/opted-out remain
  server-enforced.
- **preferred (score boosts):** high-energy sector, `open_7_days`, multi-location.
- **scoring_profile_key:** **`utility_energy`** (the existing profile — it already ranks energy-usage
  likelihood, boosting high-energy sectors). No new profile code.
- **gated_signals:** none.

**Availability:** **100% on current lawful attributes** — OSM stamps
country/region/city/phone/email; role-email is derived; `utility_energy` already exists. Buildable end
to end with zero new sources.

---

## 7. SEEDED CAMPAIGN 2 — "Business Restructuring" (firmographic today; financial data GATED)

**Intent:** business owners/operators, size startup → large — as **lawful firmographic/contactability
targeting**.

### 7.1 Read-time targeting (lawful today)
**Compiles to (v2 composition), using ONLY predicates available now:**
```
op: AND, nodes: [
  { predicate: "firmographic.business_type", params: {in: [...buyer-selected sectors...]} },
  { predicate: "firmographic.independent",   params: {} },      # owner-operated/independent vs chain
  { predicate: "geo.area",                   params: {region|city: "{area}"} },
  { predicate: "contactability.has_business_contact", params: {} }
]
```
- `firmographic.independent` = owner-operated/independent vs chain — DERIVE from `attributes.brand` /
  cross-lead aggregation (v2 §8.1), where determinable; absent ⇒ unknown ⇒ non-match (tri-state).
- **preferred (boosts):** owner-operated independents; **size band WHERE lawfully available** — today no
  lawful size source exists, so this boost simply **does not apply** (no boost, never a penalty, never a
  fabricated size). It activates only if/when a licensed firmographic source is added.
- **scoring_profile_key:** `campaign_weighted` (or a `restructuring_fit` profile) — **firmographic
  only; reads NO financial fields.**

### 7.2 HARD COMPLIANCE BOUNDARY — MCA / debt / lender (the important part)

The fields **`has_mca`**, **`amount_owed`**, **`lender`** are **PRIVATE FINANCIAL DATA**. No current
adapter (OSM, urlscan) can lawfully produce them.

- **No inference, no guessing, no fabrication.** The tool MUST NOT present a business as "has an MCA /
  owes £X / lender Y" without a **real sourced value**. There is **no heuristic, no placeholder, no
  inferred value** — ever.
- **Modeled as OPTIONAL enrichment attributes** (`attributes.has_mca`, `attributes.amount_owed`,
  `attributes.lender`) that **only ever populate from a dedicated, GATED Signal Acquisition source**
  (Targeting v2 §12, deferred). Such a source may be added **ONLY** if it:
  1. has a **documented lawful basis** to hold and resell business financial data;
  2. clears the **existing compliance gate** — source/license/`lawful_basis` metadata (the `Lead`
     already carries `lawful_basis`), opt-out/suppression coverage, and the buyer **compliance
     acknowledgement**;
  3. is **explicitly signed off by the project's compliance owner before ingest** — because targeting by
     financial distress is legally and ethically sensitive and **may involve sole-trader personal data**
     (the individual is the business), which pulls it under the people-data gate (v2 §11).
- **Until such a source exists and passes the gate:** the Restructuring campaign runs on **firmographic
  targeting only**, and the MCA/debt/lender fields render as **"not available — requires licensed
  source"** in the UI (via `gated_notices`). Do **NOT** stub them with placeholder or inferred values.
- **Any predicate that filters on these fields is part of the gated Signal Acquisition scope, NOT the
  read-time targeting layer**, and inherits tri-state null-handling: absent ⇒ unknown ⇒ **non-match,
  including under negation**. So even if a `financial.has_mca` predicate is declared, with no licensed
  source populating it every lead is `unknown` → the filter matches **nothing** (it can never
  fabricate matches), and its negation likewise excludes all (never surfaces un-sourced businesses).

`gated_signals_json` for this campaign therefore declares
`["attributes.has_mca","attributes.amount_owed","attributes.lender"]` — surfaced as unavailable, never
compiled into the read-time composition, until §7.3 is satisfied.

### 7.3 Path to enabling financial targeting (future, gated — NOT this build)
A future Signal Acquisition source + its predicates (`financial.has_mca`, `financial.amount_owed`,
`financial.lender`) may be specced **separately** once (1)–(3) above are met. It lands as a gated
provider that stamps the attributes with real sourced values + full source/license/lawful_basis
metadata; the read-time predicates then read them under the standard tri-state rules. Not in scope now.

---

## 8. Which requirements run on current lawful attributes vs gated

| Campaign requirement | Attribute(s) | Provider today | Status |
|---|---|---|---|
| **Utilities (UK):** UK + area + usable business contact | `country`,`region`,`city`,`phone`,`public_email` | OSM (+ role-email derive) | **NOW — 100% lawful today** |
| Utilities ranking (energy fit) | category/`open_7_days`/multi-location | OSM + `utility_energy` profile | **NOW** |
| **Restructuring:** business type / sector | `category_keys` | OSM taxonomy | **NOW** |
| Restructuring: independent vs chain | `attributes.brand` / cross-lead | OSM brand (via §12) / DERIVE | **NOW (DERIVE) / partial** |
| Restructuring: location + business contact | `country`/`region`/`city`,`phone`,`public_email` | OSM | **NOW** |
| Restructuring: **size band** | `attributes.size_band` | — | **GATED — NEW licensed firmographic source** |
| Restructuring: **has_mca / amount_owed / lender** | `attributes.has_mca/amount_owed/lender` | — | **GATED — licensed financial source + compliance-owner signoff (§7.2). NEVER inferred.** |

---

## 9. Grep-clean + masking/compliance guarantees

- **Grep-clean core:** `grep -rinE "campaign|utilit|restructur|mca|lender|amount_owed" app/core/` →
  empty. `app/core/` keeps only the generic Segment/composition/predicate/registry/rollup machinery from
  v2. Campaign model + compile + seed live under `app/campaigns/`; scoring profiles under
  `app/scoring/profiles/`; the gated financial source (deferred) under `app/signals/`. Campaign/vertical/
  financial strings never enter core.
- **Compliance spine unchanged:** a campaign only emits a composition. Masking, credit-unlock,
  suppression/opt-out, retention, and audit apply to campaign-matched leads exactly as to any Segment
  (v2 §7/§11). A suppressed/opted-out lead matched by a campaign is still blocked at search, preview,
  unlock, and export.
- **No fabrication:** the tri-state rule guarantees that any field with no lawful source (financial,
  size) is `unknown` and can never produce a match or a displayed value; the UI shows "not available —
  requires licensed source." This is enforced, not advisory.

---

## 10. Module layout (extends v2 §14)

```
app/campaigns/
  models.py     # Campaign (lv_campaign) + Segment.source_campaign_key — OUTSIDE core (no "campaign" in core)
  compile.py    # compile_campaign(campaign, buyer_params) -> CompiledCampaign (generic transform)
  crud.py       # admin CRUD + list-active
  seed.py       # SEEDED campaigns: "Utilities (UK)", "Business Restructuring" (strings live here)
app/scoring/profiles/
  campaign_weighted.py   # generic boost profile driven by preferred_json (no campaign strings)
  utility_energy.py      # existing — reused by Campaign 1
app/signals/             # DEFERRED Signal Acquisition (gated financial/size sources) — NOT built now
app/web/routes_buyer.py + templates   # Campaign selector -> compile -> populate composer
app/core/ …              # UNCHANGED generic v2 machinery; no campaign/vertical/financial strings
```

Note: `lv_campaign` is created because `app/campaigns/models.py` is imported at startup before
`init_db`, so `SQLModel.metadata.create_all` includes it (same pattern as the existing models).

---

## 11. Invariants & test obligations (extend v2 §15)

- **INV-6 (no-fabrication of unsourced fields):** with no licensed source registered, a filter on a
  gated field (`has_mca`/`amount_owed`/`lender`/`size_band`) matches **zero** leads (tri-state
  `unknown`), its negation surfaces **no** un-sourced leads, and no lead ever carries or displays a
  placeholder/inferred financial value; the UI renders "not available — requires licensed source."
  **Test:** assert zero matches + zero fabricated values + the unavailable notice, with no gated source
  loaded.
- **INV-7 (campaign = composition, spine unchanged):** a campaign-compiled Segment yields the same
  masking/suppression/opt-out/audit behavior as a hand-built Segment; a suppressed/opted-out lead
  matched by a campaign is blocked at search/preview/unlock/export. **Test:** parity with a hand-built
  equivalent composition + the compliance-block assertions.
- **INV-8 (cross-category):** a campaign composition contains no single-category filter unless the
  campaign explicitly declares one (Utilities has none). **Test:** Utilities composition has no
  `category` predicate; matches leads spanning ≥2 categories.
- **INV-9 (grep-clean core):** no `campaign|vertical|financial` strings in `app/core/`. **Test:** the
  grep gate.
- **INV-10 (audit):** campaign create/select/search are audited. **Test:** an audit row per event.
- Inherits **INV-1..INV-5** from Targeting v2 (tri-state, role-email allowlist, masking, grep, pushdown
  soundness).

---

## 12. Build sequencing & decomposition

- **Order:** pilot green → Targeting v2 (its 3 plans, v2 §14) → **then** Campaign layer.
- **Campaign layer plan (single, small — it's a preset over v2):** `Campaign` model + `compile_campaign`
  + CRUD + seed the **two** campaigns + the generic `campaign_weighted` profile + the selector UI +
  audit events + INV-6..INV-10 tests. Campaign 1 ships fully functional; Campaign 2 ships firmographic
  with the financial fields gated/"not available."
- **Deferred (separate specs):** the gated Signal Acquisition financial/size sources (§7.3) — each
  requires its own lawful-basis review + compliance-owner signoff before any code.

---

## 13. Acceptance criteria (for the eventual build, not now)

1. A campaign is a DB row; adding one = data (+ optional profile), no `app/core` change; grep-clean
   (INV-9).
2. Selecting a campaign compiles to a v2 composition + scoring profile and populates the composer;
   buyer can tweak and save as a Segment (with `source_campaign_key`).
3. "Utilities (UK)" runs end to end on current lawful attributes, cross-category (INV-8), ranked by
   `utility_energy`.
4. "Business Restructuring" runs on firmographic/contactability today; MCA/debt/lender/size render "not
   available — requires licensed source"; no inferred/placeholder values exist (INV-6).
5. Campaign-matched leads inherit masking/suppression/opt-out/retention/audit unchanged (INV-7).
6. Campaign create/select/search audited (INV-10).
7. The gated financial predicates live in the deferred Signal Acquisition scope, never the read-time
   composition, and inherit tri-state null-handling.
```
