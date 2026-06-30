# LeadVault — Composable Targeting / Segmentation Layer (Design Spec, v2)

**Date:** 2026-06-30
**Status:** SPEC ONLY — for review. **Do NOT build yet.** Sequenced strictly AFTER the pilot-readiness
checklist is green; not to be interleaved with pilot hardening.
**Supersedes:** `2026-06-30-targeting-segmentation-design.md` (v1). v2 folds in the review findings
(C1, I1–I4, M1–M5). Architecture is unchanged from v1; the changes are evaluation-semantics and
scope-boundary corrections. See §16 Changelog.
**Scope:** a composable Targeting/Segmentation layer for the Recipe Builder — buyers compose filters &
signals (AND/OR groups), name and save them as reusable Segments, and get a live estimate, instead of
today's single coarse recipe.

---

## 1. Goal

Replace the coarse recipe (`DEFAULT_FILTERS`) with a **composable predicate graph**. A buyer picks
targeting dimensions, sets parameters, combines them with AND/OR (+ per-leaf negation), sees the
resulting count + quality/freshness distribution + masked samples update live, and can **save the
composition as a named Segment** to reuse.

Everything downstream of "which leads match" is unchanged: **masking, credit-unlock, suppression,
opt-out, retention, and audit logging are server-enforced exactly as today.** The targeting layer only
decides the candidate set; it never touches the compliance spine.

**Two subsystems, cleanly split (I1):**
- **Targeting (this spec, buildable):** *read-time* predicates over signals already stamped on leads.
- **Signal Acquisition (§12, deferred):** *write-time*, admin-gated, async jobs that *populate* a new
  signal (custom fingerprint, keyword crawl, careers detection) which a predicate later reads. The
  builder never synchronously crawls/enriches inventory.

---

## 2. Architecture principles (non-negotiable, mirror existing discipline)

1. **Filters are predicate plugins** — same pattern as scoring profiles (`register/get/all_keys`).
   Adding a dimension = registering a predicate. The marketplace core never names a concrete filter.
2. **Predicates read the NORMALIZED lead view, never raw source fields** — canonical dotted paths
   (`country`, `intent.online_ordering_detected`, `attributes.detected_platform`) assembled from `Lead`
   columns + `attributes_json` + `intent_json` + `subscores_json` + category links.
3. **Data-driven UI.** Providers DECLARE the attributes they populate; a maintained
   **populated-paths rollup** (§6) reflects actual inventory coverage; the builder offers a filter only
   when its required paths are populated, with a "populated on N% of inventory" figure.
4. **Composition.** Filters combine with AND/OR groups + per-leaf negation; a composition is named and
   saved as a **Segment**. **Estimate** (count + score/freshness distribution + masked samples)
   recomputes (debounced, cached) as the composition changes.
5. **Compliance spine unchanged & server-enforced.** Masking, credit-unlock, suppression/opt-out
   (always on), retention, and audit apply to filtered results exactly as today.
6. **Grep-clean core.** `app/core/` holds only the generic engine (view, composition evaluator,
   predicate registry, Segment model/CRUD, rollup). No vertical/source/entity/platform strings in
   `app/core/`. Concrete predicates and their strings live in `app/targeting/predicates/` and (vertical
   ones) alongside the scoring profile. Buyer tokens (a platform name, an entity domain) travel as
   **params/data** in the saved composition — never as code in core.

---

## 3. The normalized lead view (the namespace predicates read)

`app/core/targeting/view.py` — `lead_view(lead) -> dict`, generic (reads only `Lead` columns + the JSON
blobs; no hardcoded signal names):

```
{ "id","business_name","category_keys",
  "city","region","country","postal_code","latitude","longitude",
  "phone","public_email","website_url","opening_hours",
  "score_total","subscores":{...},          # contactability/freshness/confidence/fit/...
  "attributes":{...attributes_json},         # open_7_days, detected_platform, matched_fingerprint, ...
  "intent":{...intent_json},                 # website_reachable, ssl, online_ordering_detected, ...,
                                             #   last_scanned  (presence ⇒ web-enriched)
  "source_key","source_license","scoring_profile_key",
  "date_discovered","date_last_verified","retention_expiry","times_sold" }
```

Predicates address values by dotted path. The builder is generic — new attributes become addressable
automatically when a provider stamps them.

---

## 4. Predicate-plugin interface + tri-state evaluation (C1 — INVARIANT)

`app/core/targeting/predicate.py` (generic contract):

```python
@runtime_checkable
class Predicate(Protocol):
    key: str            # dotted id: "geo.radius", "web.has_online_ordering", "tech.platform"
    group: str          # dimension group
    label: str
    reads: list[str]    # normalized view paths it requires, e.g. ["latitude","longitude"]
    params_schema: dict
    def matches(self, view: dict, params: dict) -> bool | None: ...   # None == UNKNOWN
```

### 4.1 Tri-state semantics (INVARIANT — must be enforced and tested)

A predicate whose required path is **absent/empty** on a lead returns **`None` (unknown)** — it must
NOT guess `False`. Evaluation uses **Kleene three-valued logic**, and a lead is included **iff the
whole composition evaluates to `True`** (`None` and `False` both exclude):

- Leaf: `True` / `False` / `None` (unknown when a read path is absent).
- `negate`: `not True = False`, `not False = True`, **`not None = None`** (unknown stays unknown).
- `AND`: `False` if any child `False`; else `None` if any child `None`; else `True`.
- `OR`: `True` if any child `True`; else `None` if any child `None`; else `False`.
- Empty `AND` ⇒ `True`; empty `OR` ⇒ `False`; empty composition ⇒ `True` (then suppression/opt-out
  still apply downstream).

**Why this is non-negotiable:** it is the same failure class as the opt-out exact-match bug we fixed —
silently wrong, passes naive tests. On an un-enriched OSM lead, `intent.ecommerce_detected` is unknown,
so:
- `web.has_ecommerce` ⇒ unknown ⇒ **excluded** (we only want leads *known* to have it).
- `NOT web.has_ecommerce` ⇒ `negate(None) = None` ⇒ **excluded** (we return only leads *known not* to
  have it — never un-enriched leads). This is the exact behavior the review demanded.

**`web.is_enriched` predicate:** returns `True` iff the lead has been web-enriched
(`intent.last_scanned` present), else `False` (never unknown). Lets a buyer explicitly require
"signal was actually evaluated."

**Test obligation (MUST ship with the build):** a regression test asserting that a `NOT <signal>`
filter (e.g. `NOT web.has_ecommerce`) **excludes un-enriched leads** and includes only leads known to
lack the signal; plus tri-state truth-table tests for `negate`/`AND`/`OR` including the unknown rows.

`app/core/targeting/registry.py` (mirror of the scoring-profile registry):
`register / get(key) / all_keys() / available(populated_paths: set[str]) -> [Predicate]` (data-driven:
`reads ⊆ populated_paths`). Concrete predicates register at startup via `register_targeting_runtime()`.

---

## 5. Composition model + canonical negation (I4)

**Composition** = a boolean tree (`app/core/targeting/composition.py`), stored as JSON. **One** negation
mechanism — a per-leaf `negate` flag — and **binary groups only** (`AND` / `OR`). There is **no
`NOT`-group op** (it was ambiguous; per-leaf `negate` covers it).

```json
{ "op": "AND", "nodes": [
    { "predicate": "geo.country", "params": {"value": "GB"} },
    { "op": "OR", "nodes": [
        { "predicate": "web.has_online_ordering", "params": {} },
        { "predicate": "tech.platform", "params": {"platform": "<buyer-supplied>"} } ] },
    { "predicate": "web.has_ecommerce", "params": {}, "negate": true } ] }
```

- Leaf = `{predicate, params, negate?}`; group = `{op: AND|OR, nodes:[...]}`.
- `evaluate(view, node) -> bool | None` walks the tree with the §4.1 Kleene logic; the top-level
  decision includes a lead iff `evaluate == True`. Pure, generic, no concrete predicate names in core.
- Empty-group / empty-composition semantics per §4.1.
- **`exclude.*` predicates are thin sugar over `negate`** — `exclude.domain` ≡ a negated domain-match
  leaf — so there is exactly one underlying exclusion mechanism. The always-on exclusions
  (suppressed/opted-out) are NOT predicates; they remain server-enforced in the compliance spine and
  cannot be toggled off.

**Segment** = a saved composition. New model `Segment` (`lv_segment`) in `app/core/db.py`:
`id, buyer_account_id (indexed, owned), name, composition_json, created_at, updated_at`. Buyer-scoped;
ownership guarded like `PurchasedLead`.

---

## 6. Provider declarations + populated-paths rollup (I3, M2)

Two inputs decide which filters appear:

1. **Provider capability declarations.** `SourceMeta.provides: list[str]` (adapters) and an equivalent
   for enrichers declare the normalized paths they can populate — powers a forward-looking "available if
   you ingest from <source>" hint.
2. **Populated-paths rollup (the primary gate).** A small maintained table
   `lv_attribute_coverage(path, populated_count, total_count, updated_at)` is **updated incrementally at
   ingest/enrich time** — NOT recomputed by an O(inventory) JSON scan on every builder load. The builder
   offers a predicate when its `reads` are present in the rollup and shows **"populated on N% of
   inventory."** (Bootstrap/backfill: a one-off recompute job seeds the rollup for existing inventory.)

**M2 — availability ≠ will-match.** A path being populated means the filter is *offerable* (filterable);
it does **not** promise the buyer's specific value matches anything. The live **estimate carries the
real count** — a `tech.platform=shopify` filter may be offered yet estimate to 0.

---

## 7. Integration with the marketplace + two-stage evaluator (I2, M1, M4)

- **Selection.** `matching_by_composition(session, composition, *, exclude_lead_ids) -> list[Lead]` is
  the Segment chokepoint. **M1 decision:** the legacy coarse recipe keeps using `recipes.matching_leads`
  unchanged; Segments use `matching_by_composition`. No translator is written (the two coexist; a trivial
  translator may be added later only if free).
- **Two-stage evaluator (I2).** To not undo the P2-A indexing work:
  1. **SQL pre-narrow (sound pushdown only).** Leaf predicates that are (a) over **indexed columns**
     (`country`, `region`, `city`, `score_total`, `source_key`, `date_*`, category via
     `lv_lead_category_link`), (b) **always-known** (column-backed, never unknown), and (c) in a
     **top-level AND (non-negated)** position compile to a SQL `WHERE` that narrows candidates. Pushdown
     is **conservative** — it only ever pre-filters when provably sound (never drops a lead that could
     match); OR-branches, negation, and JSON/`intent`/`attributes` predicates are NOT pushed.
  2. **Python tri-state pass.** The full §4.1 evaluation runs over the narrowed candidate set,
     producing the authoritative result. The SQL stage is an optimization; correctness is defined by
     stage 2.
- **Estimate.** Returns `count`, `score_distribution`, `freshness_distribution`, and up to N **masked**
  samples (`mask_preview`). It is **debounced** (no recompute per keystroke), **cached** by composition
  hash, and bounded by a **candidate cap** (configurable; beyond it the estimate is reported as a
  lower-bound "N+"). Server-enforced masking on samples — identical guarantee to the marketplace cards.
- **Compliance spine unchanged.** After selection, `marketplace.search`/unlock/export keep every existing
  step: `is_expired` skip, suppression skip, `lead_opted_out` skip, `mask_preview`, ownership/credit
  checks, audit. No compliance behavior changes.
- **Audit the targeting act (M4).** Segment **create/update** and Segment-driven **search** are written
  to the audit log (`actor`, segment id, composition hash) — "who targeted what" — alongside the
  existing unlock/export audit.

---

## 8. Targeting catalog — read-time filters (signals already stamped)

Only **read-time** filters appear here. Items that must first *create* a signal are NOT filters — they
live in **Signal Acquisition (§12)** and, once they populate an attribute, are read by the matching
filter below. **Avail:** **NOW** = current adapters/enrichers already stamp it · **DERIVE** = computed
from existing fields · **NEW SOURCE** = needs a new lawful adapter (read-time once it lands). "Lives in"
shows grep-clean placement.

### 1. Firmographic
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Business category/type | `category_keys` | OSM (DB taxonomy) | predicates/firmographic | NOW |
| Independent vs chain (by brand) | `attributes.brand` | OSM brand (once captured by Signal Acq.) / cross-lead | firmographic | DERIVE / via §12 |
| Single- vs multi-location | `attributes.number_of_locations` | cross-lead brand/name aggregation | firmographic | DERIVE |
| Size band | `attributes.size_band` | — | firmographic | NEW SOURCE |
| Company age / newly-registered | `attributes.registered_on` | — | firmographic | NEW SOURCE |

### 2. Geographic
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Country / region / city | `country`,`region`,`city` | OSM | predicates/geo | NOW (indexed → SQL pushdown) |
| Radius around a point | `latitude`,`longitude` | OSM | geo | NOW (haversine, Python) |
| Postal area | `postal_code` | OSM | geo | NOW (coverage varies; rollup shows %) |
| TLD heuristic | `website_url` (parse) | DERIVE | geo | NOW |
| Exclude regions | `country`/`region`/`city` (negate) | OSM | geo | NOW |

### 3. Technographic ("uses platform X") — read-time only
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Runs a detected platform | `attributes.detected_platform`,`attributes.on_platform`,`attributes.matched_fingerprint` | fingerprint adapter | predicates/technographic | NOW (for fingerprints already run) |
| Uses online-ordering/booking/payments/ecommerce | `intent.*` | website-enrich | technographic | NOW |
| Custom platform/fingerprint | `attributes.matched_fingerprint` | **§12 Signal Acquisition** populates it; this filter then reads it | technographic | filter = NOW once signal acquired |

> Generalized GloriaFood mechanism: the platform is a **param** the buyer picks/types; the predicate
> compares it to the stamped signal. A *new* custom fingerprint is acquired via §12, then filtered here.

### 4. Association-to-entity ("connected to entity E") — read-time only
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Embeds entity's widget / on entity's platform | `attributes.matched_fingerprint` (entity tokens) | fingerprint adapter | predicates/association | NOW (e.g. GloriaFood = `fbgcdn.com`) |
| Links to entity (outbound link) | `attributes.links_to` | **§12** records outbound hosts; filter reads it | association | filter = NOW once acquired |
| Listed in entity's directory / on review platform | `attributes.listed_in` | directory/review **NEW SOURCE** adapter | association | NEW SOURCE |

> Entity (vendor/platform/marketplace/supplier/directory/review site) is a **buyer-supplied param**.

### 5. Web-presence / webographic — read-time only
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Has a website vs none | `website_url` | OSM | predicates/webpresence | NOW |
| Site reachable | `intent.website_reachable` | website-enrich | webpresence | NOW |
| Online-ordering / booking / e-commerce / payments | `intent.*` | website-enrich | webpresence | NOW |
| SSL | `intent.ssl` | website-enrich | webpresence | NOW |
| Was web-enriched | `intent.last_scanned` | website-enrich | webpresence | NOW (`web.is_enriched`) |
| On-page keyword / page-type (careers/hiring) | `intent.matched_keywords`,`intent.page_types` | **§12** populates; filter reads | webpresence | filter = NOW once acquired |
| Last-updated / freshness | `date_last_verified`,`intent.last_scanned` | enrich | webpresence/freshness | NOW |

### 6. Contactability (business-role only — see §11)
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Has email / has phone | `public_email`,`phone` | OSM/fingerprint | predicates/contactability | NOW |
| Role-based published contact | `public_email` (prefix ∈ fixed allowlist) | DERIVE | contactability | NOW — **business-role allowlist only (§11 invariant)** |
| Has social profile | `attributes.social` | **§12** | contactability | filter = NOW once acquired |

### 7. Intent / lifecycle
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Recently discovered / verified | `date_discovered`,`date_last_verified` | platform | predicates/freshness | NOW |
| Recently opened/registered/moved/expanding | `attributes.lifecycle_*` | — | (profile/adapter) | NEW SOURCE (each tagged w/ source) |
| Hiring | `intent.page_types` (careers) | **§12** (proxy) / job-board **NEW SOURCE** | webpresence | via §12 / NEW SOURCE |

### 8. Vertical-specific signals (live with the scoring profile, NOT core)
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Cuisine, delivery radius, opening hours, etc. | profile-declared paths | the profile's adapter (+ §12 for new captures) | scoring/profiles/<vertical>_predicates | NOW (opening hours) / via §12 |

### 9. Exclusions (thin sugar over `negate`)
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Exclude already-purchased | `times_sold` / `PurchasedLead` | platform | predicates/exclusions | NOW |
| Exclude suppressed / opted-out | — (always on, server-enforced, not a predicate) | compliance spine | core (unchanged) | NOW |
| Exclude domains / TLDs / competitors | `website_url` | DERIVE | exclusions | NOW |
| Exclude below min score / confidence | `score_total`,`subscores.confidence` | scorer | exclusions | NOW (score → SQL pushdown) |

### 10. Freshness / verification / confidence
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Discovered / verified within N days | `date_discovered`,`date_last_verified` | platform | predicates/freshness | NOW (date → SQL pushdown) |
| Min confidence threshold | `subscores.confidence` | scorer | freshness | NOW |
| Source-type filter (ODbL-only / fingerprint-confirmed) | `source_key`,`source_license`,`scoring_profile_key` | SourceMeta.type | predicates/source | NOW (source_key → SQL pushdown) |

---

## 9. Data-driven Recipe Builder UI + saved Segments

- The builder is a **composer**: choose a dimension group → see only predicates whose `reads` are in the
  rollup (others shown disabled with "needs source X" + the populated-% figure) → set params via
  `params_schema` → group with AND/OR + per-leaf negate → **live Estimate panel** (count + score &
  freshness histograms + N masked samples), **debounced + cached**.
- **Save as Segment**: name the composition; it persists and reappears for re-use, re-estimation, and
  as the basis of a marketplace search/unlock flow.
- The UI renders entirely from `registry.available(rollup_paths)` + each predicate's `params_schema` —
  no hardcoded filter list. New predicate = new option, no UI edit.

---

## 10. (reserved — see §11 Compliance)

## 11. Compliance — the bright line (non-negotiable)

- **Default scope stays BUSINESS-LEVEL.** "Targeting a category of people" is ONLY role/function-based
  **business** targeting: owner-operated independents (firmographic) or a published **business-role**
  contact. NEVER named-individual profiles; NEVER special-category/protected attributes; no predicate
  may key on a protected attribute.
- **Role-email is a compliance INVARIANT (M3).** The role-based-contact predicate matches `public_email`
  **only** against a **fixed role-prefix allowlist** (`info@`, `sales@`, `support@`, `hello@`,
  `contact@`, `enquiries@`, `admin@`, `office@`, …) and **NEVER** an arbitrary local-part such as
  `firstname.lastname@`. This is the line between business-role and individual targeting.
  **Test obligation:** a test asserting the predicate matches the role allowlist and rejects a
  personal-looking local-part (`john.smith@…` → no match).
- **Named decision-maker (personal) data = SEPARATE, GATED, DEFERRED.** Future-only; requires ALL of: a
  lawful source with documented lawful basis; the buyer compliance acknowledgement; opt-out/suppression
  coverage; routing through the compliance spine (mask/suppress/audit). **Not built now.**
- Every predicate that could surface a personal-ish field (e.g. `public_email`) still flows through
  masking, suppression/opt-out, and audit — the targeting layer cannot bypass the spine.

---

## 12. Signal Acquisition subsystem (DEFERRED — write-time, admin-gated, async) (I1)

Read-time targeting filters on signals that already exist. **Creating** a signal that isn't stamped yet
is a different operation and a separate subsystem:

- **What it covers:** running a *new* custom fingerprint over inventory; on-page keyword extraction;
  page-type/careers detection; outbound-link capture; OSM brand/cuisine capture; social-profile capture.
  (These are the v1 "ENRICH+" items, moved out of the filter path.)
- **Properties:** **write-time** (mutates `attributes_json`/`intent_json`), **async/batched** (can take
  minutes over inventory), **compute-costing**, and **admin-gated** (a buyer cannot synchronously
  re-crawl inventory from the builder). It runs as an ingestion-class job and updates the
  populated-paths rollup; afterward the corresponding read-time predicate (§8) simply works.
- **Status:** **deferred** — its own spec + (where external) lawful-basis review. The first targeting
  build does NOT include it; targeting ships against already-stamped signals.

---

## 13. Grep-clean + compliance guarantees (acceptance)

- `grep -rinE "energy|utility|osm|overpass|<platform/entity tokens>" app/core/` → empty. Core =
  `view.py`, `composition.py`, `predicate.py`, `registry.py`, Segment model/CRUD, rollup — all generic.
  Concrete predicate keys/strings live in `app/targeting/predicates/*` and
  `app/scoring/profiles/*_predicates.py`. Buyer tokens are **params in `composition_json`** (data rows).
- Masking/suppression/opt-out/retention/audit: proven unchanged by reusing the exact
  `marketplace.search` post-selection pipeline; tests assert a Segment-matched, opted-out, or suppressed
  lead is still excluded/masked/blocked at search, preview, unlock, and export.

---

## 14. Module layout & build decomposition (M5)

```
app/core/db.py                       # + Segment (lv_segment) + AttributeCoverage (lv_attribute_coverage)
app/core/targeting/
  view.py  predicate.py  registry.py  composition.py  segments.py  rollup.py     # all generic
app/targeting/predicates/            # CONCRETE predicates (strings here, NOT core)
  geo.py webpresence.py contactability.py freshness.py source.py exclusions.py
  firmographic.py technographic.py association.py
app/scoring/profiles/<vertical>_predicates.py   # vertical-specific predicates
app/targeting/runtime.py             # register_targeting_runtime()
app/adapters/base.py                 # + SourceMeta.provides
app/web/routes_buyer.py + templates  # composer UI, live estimate, save/list Segments
```

**Build decomposition — three plans (do NOT build until pilot is green):**
1. **Engine plan** — `view` + `predicate` + tri-state `composition` evaluator (with the §4.1 truth-table
   + "NOT excludes un-enriched" regression tests) + `Segment` model/CRUD + `estimate` (debounced/cached)
   + the two-stage evaluator + ~6 **NOW** predicates (geo, score/source/date, category, has-contact,
   web-presence). Server-only; proves grep-clean + compliance-unchanged.
2. **Composer UI plan** — data-driven builder, AND/OR + negate, live estimate panel, save/list/re-estimate
   Segments, `lv_attribute_coverage` rollup + provider `provides` declarations + "populated N%" display.
3. **Predicate-pack plan(s)** — technographic/association/firmographic/vertical predicate packs +
   exclusions sugar, landing as their read-time signals exist.

(Signal Acquisition §12 and NEW-SOURCE adapters are separate, later specs.)

---

## 15. Invariants & test obligations (codified)

- **INV-1 (tri-state, C1):** unknown over absent paths; `not None = None`; include iff composition
  `== True`. **Test:** truth-table for negate/AND/OR incl. unknown rows; **and** `NOT <signal>` excludes
  un-enriched leads.
- **INV-2 (role-email, M3):** role-contact predicate matches a fixed role-prefix allowlist only, never a
  personal local-part. **Test:** allowlist matches; `john.smith@` does not.
- **INV-3 (masking/spine):** Segment-matched leads remain masked + suppression/opt-out-filtered + audited
  at search/preview/unlock/export. **Test:** opted-out/suppressed lead matched by a Segment is still
  blocked everywhere.
- **INV-4 (grep-clean):** no vertical/source/entity strings in `app/core/`. **Test:** the grep gate.
- **INV-5 (pushdown soundness, I2):** the SQL pre-narrow never drops a lead the Python tri-state pass
  would include. **Test:** parity between two-stage and pure-Python evaluation on a fixture set.

---

## 16. Changelog from v1 (what moved)

- **§1, §12 (I1):** split **read-time Targeting** from a deferred, admin-gated, async **Signal
  Acquisition** subsystem. All v1 "ENRICH+/create-the-signal" items (custom fingerprint, keyword,
  careers/page-type, outbound-link, brand/cuisine, social) moved OUT of the filter catalog into §12;
  §8 filters now read only already-stamped signals.
- **§4 (C1):** predicates return `bool | None`; **Kleene tri-state** evaluation defined; `not None =
  None`; include iff `True`; added `web.is_enriched`; made it INV-1 with a mandatory "NOT excludes
  un-enriched" regression test.
- **§5 (I4):** one negation mechanism — per-leaf `negate` + binary `AND`/`OR` only; dropped the
  ambiguous `NOT`-group; defined empty-AND=all / empty-OR=none / empty-composition=all; `exclude.*`
  is now thin sugar over `negate`.
- **§7 (I2):** two-stage evaluator (sound SQL pushdown for indexed, always-known, top-level-AND leaves →
  Python tri-state pass); estimate **debounced + cached + candidate-capped**. (M1) keep `matching_leads`
  for legacy recipes, add `matching_by_composition` for Segments, no translator. (M4) audit Segment
  create/search.
- **§6 (I3, M2):** `attribute_index` replaced by a maintained `lv_attribute_coverage` **rollup** updated
  at ingest (not an O(inventory) per-load scan), with a "populated on N%" figure; "available =
  filterable; the estimate carries the real count."
- **§11 (M3):** role-email allowlist promoted to a compliance INVARIANT (INV-2) with a test.
- **§14 (M5):** explicit **three-plan decomposition** (engine → composer UI → predicate packs).
- **§15:** new **Invariants & test obligations** section codifying INV-1..5.
- Unchanged from v1 (and kept): predicate-plugin pattern, normalized-view indirection, grep-clean
  placement, the §11 compliance bright line + gated people-data deferral, and the honest
  NOW/NEW-SOURCE availability mapping.

---

## 17. Acceptance criteria (for the eventual build, not now)

1. Predicate registry + composition evaluator generic; `app/core/` grep clean (INV-4).
2. Tri-state evaluation per §4.1; `NOT <signal>` excludes un-enriched leads (INV-1).
3. Builder offers only predicates whose required paths are in the coverage rollup; renders from
   registry + `params_schema` (no hardcoded list); shows populated-%.
4. Estimate = count + score/freshness distributions + masked samples; debounced/cached/capped; masking
   server-enforced (INV-3).
5. A Segment can be named, saved, listed, re-estimated, drive a search; buyer-owned; create/search
   audited.
6. Two-stage evaluator parity with pure-Python eval (INV-5); legacy `matching_leads` untouched.
7. Role-email allowlist invariant holds (INV-2); no people-level data path exists; §12 deferred.
```
