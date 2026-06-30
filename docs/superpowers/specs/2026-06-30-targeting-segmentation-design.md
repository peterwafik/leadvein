# LeadVault — Composable Targeting / Segmentation Layer (Design Spec)

> ⚠️ **SUPERSEDED by `2026-06-30-targeting-segmentation-design-v2.md`.** v2 folds in the review
> findings (tri-state null handling, read-time vs write-time split, two-stage evaluator, canonical
> negation, and the minors). Kept for history; do not build from this version.

**Date:** 2026-06-30
**Status:** SUPERSEDED (was: SPEC ONLY — for review). **Do NOT build yet.** Sequenced strictly AFTER the pilot-readiness
checklist is green; not to be interleaved with pilot hardening.
**Scope:** a composable Targeting/Segmentation layer for the Recipe Builder — buyers compose filters &
signals (AND/OR groups), name and save them as reusable Segments, and get a live estimate, instead of
today's single coarse recipe.

---

## 1. Goal

Replace the coarse recipe (`DEFAULT_FILTERS`: category/city/region/country/require-contact/freshness/
min-score) with a **composable predicate graph**. A buyer picks targeting dimensions, sets parameters,
combines them with AND/OR/NOT, sees the resulting count + quality/freshness distribution + masked
samples update live, and can **save the composition as a named Segment** to reuse.

Everything downstream of "which leads match" is unchanged: **masking, credit-unlock, suppression,
opt-out, retention, and audit logging are server-enforced exactly as today.** The targeting layer only
decides the candidate set; it never touches the compliance spine.

---

## 2. Architecture principles (non-negotiable, mirror existing discipline)

1. **Filters are predicate plugins** — same pattern as scoring profiles (`app/scoring/profiles/registry.py`:
   `register/get/all_keys`). Adding a targeting dimension = registering a predicate. The marketplace core
   never names a concrete filter.
2. **Predicates read the NORMALIZED lead view, never raw source fields.** A predicate consumes canonical
   keys (`country`, `intent.online_ordering_detected`, `attributes.detected_platform`, …) assembled from
   `Lead` columns + `attributes_json` + `intent_json` + `subscores_json` + category links — so a filter
   works regardless of which adapter contributed the signal.
3. **Data-driven UI.** Signal providers (adapters + enrichers) DECLARE the attributes they can populate;
   the builder additionally computes a live **attribute-presence index** over the current inventory and
   only offers a filter when its required attributes are actually populated. Source-agnostic and
   category-agnostic by construction.
4. **Composition.** Filters combine with AND/OR/NOT groups; a composition can be named and saved as a
   **Segment**. **Estimate** (count + score/freshness distribution + masked samples) recomputes as the
   composition changes.
5. **Compliance spine unchanged & server-enforced.** Masking, credit-unlock, suppression/opt-out (always
   on), retention, and audit apply to filtered results exactly as today.
6. **Grep-clean core.** `app/core/` holds only the *generic* engine (view projection, composition
   evaluator, predicate registry, Segment model/CRUD). No vertical/source/entity/platform strings
   (`energy|utility|osm|overpass|<platform>|<entity>`) appear in `app/core/`. Concrete predicates and
   their strings live in `app/targeting/predicates/` and (for vertical ones) alongside the scoring
   profile. Buyer-supplied tokens (a platform name, an entity domain) travel as **params/data** in the
   saved composition — never as code in core.

---

## 3. The normalized lead view (the namespace predicates read)

A single canonical projection, built in `app/core/targeting/view.py`:

```
lead_view(lead) -> dict   # generic; reads only Lead columns + the JSON blobs, no hardcoded signal keys
{
  "id", "business_name", "category_keys" (list, from the link table / category_keys_json),
  "city", "region", "country", "postal_code", "latitude", "longitude",
  "phone", "public_email", "website_url", "opening_hours",
  "score_total", "subscores": {...subscores_json},      # contactability/freshness/confidence/fit/...
  "attributes": {...attributes_json},                   # adapter-stamped: open_7_days, detected_platform,
                                                         #   matched_fingerprint, on_platform, ...
  "intent": {...intent_json},                           # enrich-stamped: website_reachable, ssl,
                                                         #   online_ordering_detected, booking_detected,
                                                         #   payment_provider_detected, ecommerce_detected,
                                                         #   last_scanned
  "source_key", "source_license", "scoring_profile_key",
  "date_discovered", "date_last_verified", "retention_expiry",
  "times_sold"                                           # for exclude-already-purchased etc.
}
```

Predicates address values by **dotted path** (`intent.ssl`, `attributes.detected_platform`,
`subscores.confidence`). The view builder is generic — it does not enumerate signal names, so new
attributes/intents become addressable automatically when an adapter/enricher stamps them.

---

## 4. Predicate-plugin interface

`app/core/targeting/predicate.py` (the abstract contract — generic, grep-clean):

```python
@runtime_checkable
class Predicate(Protocol):
    key: str            # stable id, dotted: "geo.radius", "web.has_online_ordering", "tech.platform"
    group: str          # dimension group: "firmographic"|"geographic"|"technographic"|...
    label: str          # UI label
    reads: list[str]    # normalized view paths it requires, e.g. ["latitude","longitude"]
    params_schema: dict # declarative form spec for the builder (types, options, help)
    def matches(self, view: dict, params: dict) -> bool: ...
```

`app/core/targeting/registry.py` (mirror of the scoring-profile registry — generic):

```python
register(predicate) / get(key) -> Predicate / all_keys() -> list[str]
available(populated_attr_keys: set[str]) -> list[Predicate]   # data-driven: reads ⊆ populated
```

- `reads` is what makes the UI data-driven: a predicate is offered only when every path in `reads` is
  present in the **attribute-presence index** (§6). It is also the grep-safe seam — the registry filters
  by declared `reads`, never by hardcoded signal names in core.
- Concrete predicates register at startup via a `register_targeting_runtime()` hook (sibling of
  `seed.register_runtime()` for adapters/profiles).

---

## 5. Composition model + Segment persistence

**Composition** = a boolean tree (`app/core/targeting/composition.py`), stored as JSON:

```json
{ "op": "AND", "nodes": [
    { "predicate": "geo.country", "params": {"value": "GB"} },
    { "op": "OR", "nodes": [
        { "predicate": "web.has_online_ordering", "params": {} },
        { "predicate": "tech.platform", "params": {"platform": "<buyer-supplied>"} } ] },
    { "predicate": "exclude.already_purchased", "params": {}, "negate": false },
    { "op": "NOT", "nodes": [ { "predicate": "geo.region", "params": {"value": "Scotland"} } ] }
] }
```

- Leaf = `{predicate, params, negate?}`; group = `{op: AND|OR|NOT, nodes:[...]}`.
- `evaluate(view, node) -> bool` walks the tree, resolving leaves through the registry. Pure, generic,
  no concrete predicate names in core.
- `matching_by_composition(session, composition, *, exclude_lead_ids) -> list[Lead]` is the new chokepoint
  (replaces/augments `recipes.matching_leads`). The current coarse `DEFAULT_FILTERS` is expressible as a
  composition, so the old recipe path is a special case (back-compatible; can be auto-translated).

**Segment** = a saved composition. New model `Segment` (`lv_segment`) in `app/core/db.py`:
`id, buyer_account_id (indexed, owned), name, composition_json, created_at, updated_at`. Buyer-scoped;
ownership guarded like `PurchasedLead`. Segments are reusable across sessions and re-estimable.

---

## 6. Signal-provider declarations + attribute-presence index (data-driven UI)

Two inputs decide which filters appear:

1. **Provider capability declarations.** Extend the provider contract with a declared capability:
   - Adapters: add `provides: list[str]` to `SourceMeta` (e.g. OSM declares
     `["category_keys","city","region","country","postal_code","latitude","longitude","phone",
       "public_email","website_url","opening_hours","attributes.open_7_days"]`).
   - Enrichers declare likewise (website-enrich declares `["intent.website_reachable","intent.ssl",
     "intent.online_ordering_detected","intent.booking_detected","intent.payment_provider_detected",
     "intent.ecommerce_detected"]`).
   These power a forward-looking "available if you ingest from <source>" hint.
2. **Live attribute-presence index** (the primary gate). `attribute_index(session) -> dict[str,int]`
   scans current inventory and returns which normalized view paths are actually populated (non-empty),
   with counts. The builder offers a predicate only when its `reads` ⊆ populated paths. This is what
   keeps the UI honest: a filter for a signal nothing in the current inventory carries is not shown
   (or shown disabled with "needs source X" from the declarations).

---

## 7. Integration with the marketplace (compliance spine unchanged)

- `marketplace.search` / `marketplace.estimate` switch their candidate selection from
  `recipes.matching_leads(filters)` to `matching_by_composition(composition)` — **and keep every existing
  step afterward**: `is_expired` skip, suppression skip, `lead_opted_out` skip, `mask_preview`
  projection, ownership/credit checks on unlock, audit on unlock/export. No compliance behavior changes.
- **Estimate** returns: `count`, `score_distribution` (histogram over `score_total` bands),
  `freshness_distribution` (over `date_last_verified` bands), and up to N **masked** samples
  (`mask_preview`, never raw contact). Recomputed on each composition edit. Server-enforced masking on
  samples — identical guarantee to the marketplace cards.
- Unlock/export of leads matched via a Segment are billed, owned, suppressed/opt-out-filtered, and
  audited exactly as today.

---

## 8. Targeting catalog — every filter, its attribute, its provider, availability

Legend for **Availability**: **NOW** = works on signals current adapters/enrichers already stamp ·
**ENRICH+** = same adapters, needs an enrichment/extraction extension · **NEW SOURCE** = needs a new
lawful adapter · **DERIVE** = computed from existing data (cross-lead or field parse). "Lives in" shows
the grep-clean placement.

### 1. Firmographic
| Filter | Reads (view path) | Provider | Lives in | Avail |
|---|---|---|---|---|
| Business category/type | `category_keys` | OSM (DB taxonomy) | targeting/predicates/firmographic | NOW |
| Size band (employees) | `attributes.size_band` | — | firmographic | NEW SOURCE (e.g. Companies House / firmographic API) |
| Company age / newly-registered | `attributes.registered_on` | — | firmographic | NEW SOURCE (company registry) |
| Independent vs chain/franchise | `attributes.brand` / derived | OSM `brand` tag (ENRICH+) or cross-lead name aggregation | firmographic | ENRICH+ / DERIVE |
| Single- vs multi-location | `attributes.number_of_locations` (derived) | cross-lead brand/name aggregation | firmographic | DERIVE |

### 2. Geographic
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Country / region / city | `country`,`region`,`city` | OSM | targeting/predicates/geo | NOW (indexed) |
| Radius around a point | `latitude`,`longitude` | OSM | geo | NOW (haversine) |
| Postal area | `postal_code` | OSM (`addr:postcode`) | geo | NOW (coverage varies) |
| TLD heuristic | `website_url` (parse) | derived | geo | NOW (DERIVE) |
| Exclude regions | `country`/`region`/`city` (negate) | OSM | geo | NOW |

### 3. Technographic ("uses platform X")
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Runs a detected platform | `attributes.detected_platform`,`attributes.on_platform`,`attributes.matched_fingerprint` | urlscan-fingerprint adapter | targeting/predicates/technographic | NOW (for fingerprints already run) |
| Uses online-ordering/booking/payments/ecommerce platform | `intent.online_ordering_detected` etc. | website-enrich | technographic | NOW |
| Custom fingerprint (buyer supplies tokens) | `attributes.matched_fingerprint` | fingerprint adapter w/ custom recipe | technographic | NOW to filter existing; a NEW custom fingerprint needs a fingerprint **enrichment pass** over inventory (ENRICH+) |

> This is the generalized GloriaFood mechanism ("find businesses that use X"): the platform name is a
> **param** the buyer picks from the recipe catalog or types; the predicate compares it to the stamped
> `detected_platform`/`matched_fingerprint`. No platform string is hardcoded in core or the predicate.

### 4. Association-to-entity ("connected to entity E")
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Embeds entity's widget / on entity's platform | `attributes.matched_fingerprint` (entity tokens) | fingerprint adapter | targeting/predicates/association | NOW (token = entity's widget/SDK; e.g. GloriaFood = `fbgcdn.com`) |
| Links to entity (outbound link) | `attributes.links_to` | website-enrich (record outbound hosts) | association | ENRICH+ |
| Listed in entity's directory | — | entity-directory discovery adapter | association | NEW SOURCE |
| Present on entity's review platform | — | review-platform adapter | association | NEW SOURCE |

> Generalizes "customers/partners of GloriaFood" to "associated with ANY entity": the entity (a vendor,
> platform, marketplace, supplier, directory, review site) is a **buyer-supplied param**; the
> embeds-widget / links-to cases reuse the fingerprint + web-presence enrichers, while
> directory/review-platform membership requires a new discovery adapter per entity class.

### 5. Web-presence / webographic
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Has a website vs none | `website_url` | OSM | targeting/predicates/webpresence | NOW |
| Site reachable | `intent.website_reachable` | website-enrich | webpresence | NOW |
| Online-ordering / booking / e-commerce / payments | `intent.*` | website-enrich | webpresence | NOW |
| SSL | `intent.ssl` | website-enrich | webpresence | NOW |
| Specific on-page keyword present | `intent.matched_keywords` | website-enrich (parameterized) | webpresence | ENRICH+ |
| Specific page type present (e.g. careers = hiring) | `intent.page_types` | website-enrich (light crawl) | webpresence | ENRICH+ |
| Last-updated / freshness | `date_last_verified`,`intent.last_scanned` | enrich | webpresence/freshness | NOW |

### 6. Contactability (business-role only — see §10)
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Has email / has phone | `public_email`,`phone` | OSM/fingerprint | targeting/predicates/contactability | NOW |
| Has social profile | `attributes.social` | ENRICH+ | contactability | ENRICH+ |
| Role-based published contact (`info@`,`sales@`,`support@`) | `public_email` (local-part parse) | derived | contactability | NOW (DERIVE) — **business-role, not individuals** |

### 7. Intent / lifecycle
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Recently discovered/verified | `date_discovered`,`date_last_verified` | platform | targeting/predicates/freshness | NOW |
| Recently opened / registered / moved / expanding | `attributes.lifecycle_*` | — | (profile/adapter) | NEW SOURCE (registry / lawful feed; each tagged w/ source) |
| Hiring | `intent.page_types` (careers) | website-enrich | webpresence | ENRICH+ (proxy) / NEW SOURCE (job boards) |
| Seasonal | `opening_hours` (heuristic) | OSM | (profile) | ENRICH+ (weak heuristic) |

### 8. Vertical-specific signals (live with the scoring profile, NOT core)
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Cuisine (restaurants) | `attributes.cuisine` | OSM `cuisine` tag | scoring/profiles/<vertical>_predicates | ENRICH+ (capture the tag) |
| Delivery radius / opening hours | `opening_hours`,`attributes.open_7_days` | OSM | scoring/profiles/<vertical>_predicates | NOW (open hours) / ENRICH+ |
| Any profile-defined signal | profile-declared paths | the scoring profile's adapter | scoring/profiles/<vertical>_predicates | per signal |

### 9. Exclusions
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Exclude already-purchased | `times_sold` / `PurchasedLead` | platform | targeting/predicates/exclusions | NOW |
| Exclude suppressed / opted-out | (always on) | compliance spine | core (unchanged) | NOW (server-enforced, not optional) |
| Exclude domains / TLDs / competitors | `website_url` | derived | exclusions | NOW |
| Exclude chains/franchises | `attributes.brand` / derived | firmographic | exclusions | ENRICH+ / DERIVE |
| Exclude below min score / confidence | `score_total`,`subscores.confidence` | scorer | exclusions | NOW |

### 10. Freshness / verification / confidence
| Filter | Reads | Provider | Lives in | Avail |
|---|---|---|---|---|
| Discovered / verified within N days | `date_discovered`,`date_last_verified` | platform | targeting/predicates/freshness | NOW |
| Min confidence threshold | `subscores.confidence` | scorer | freshness | NOW |
| Source-type filter (ODbL-only / fingerprint-confirmed) | `source_key`,`source_license`,`scoring_profile_key` | SourceMeta.type | targeting/predicates/source | NOW |

---

## 9. Data-driven Recipe Builder UI + saved Segments

- The Recipe Builder becomes a **composer**: choose a dimension group → see only the predicates whose
  `reads` are populated in current inventory (others shown disabled with "needs source X") → set params
  via `params_schema` → drop predicates into AND/OR/NOT groups → **live Estimate panel** (count +
  score histogram + freshness histogram + N masked samples) updates on every edit.
- **Save as Segment**: name the composition; it persists (`Segment`) and reappears for re-use,
  re-estimation, and as the basis of a marketplace search/unlock flow.
- The UI never hardcodes filter lists — it renders from `registry.available(attribute_index(session))`
  and each predicate's `params_schema`. New predicate = new option, no UI edit.

---

## 10. Compliance — the bright line (non-negotiable)

- **Default scope stays BUSINESS-LEVEL.** "Targeting a category of people" is implemented ONLY as
  role/function-based **business** targeting: e.g. owner-operated independents (firmographic), or
  businesses with a published `sales@`/`info@` **business-role** contact (contactability §6). It is
  NEVER assembling profiles of named individuals, and NEVER special-category/protected-attribute data.
  No predicate may key on a protected attribute.
- **Named decision-maker (personal) data = SEPARATE, GATED, DEFERRED.** If buyers later want
  person-level data, it is a future capability that requires ALL of: a lawful source with a documented
  lawful basis; the buyer compliance acknowledgement; opt-out/suppression coverage; and routing through
  the existing compliance spine (mask/suppress/audit). **Not built now.** Spec'd here only as a gated
  future item; no people-data scraping in this layer.
- Every predicate that could surface any personal-ish field (e.g. `public_email`) still flows through
  masking, suppression/opt-out, and audit exactly as the rest of the platform — the targeting layer
  cannot bypass the spine.

---

## 11. Grep-clean + compliance guarantees (acceptance)

- `grep -rinE "energy|utility|osm|overpass|<platform tokens>|<entity tokens>" app/core/` → empty.
  Core contains only: `view.py`, `composition.py`, `predicate.py`, `registry.py`, Segment model/CRUD —
  all generic. Concrete predicate keys/strings live in `app/targeting/predicates/*` and
  `app/scoring/profiles/*_predicates.py`. Buyer tokens (platform/entity/domain) are stored as **params
  in `composition_json`** (data rows), never as core code.
- Masking/suppression/opt-out/retention/audit: proven unchanged by reusing the exact
  `marketplace.search` post-selection pipeline; the test suite asserts a Segment-matched, opted-out, or
  suppressed lead is still excluded/masked/blocked at search, preview, unlock, and export.

---

## 12. Module layout

```
app/core/db.py                       # + Segment model (lv_segment) — generic
app/core/targeting/
  view.py                            # lead_view(lead) canonical projection (generic)
  predicate.py                       # Predicate protocol (generic)
  registry.py                        # register/get/all_keys/available (generic)
  composition.py                     # evaluate(view,node) + matching_by_composition (generic)
  segments.py                        # Segment CRUD, ownership-guarded (generic)
  attribute_index.py                 # populated-path index over inventory (generic)
app/targeting/predicates/            # CONCRETE predicates (strings live here, NOT core)
  geo.py  webpresence.py  contactability.py  freshness.py  source.py  exclusions.py
  firmographic.py  technographic.py  association.py
app/scoring/profiles/<vertical>_predicates.py   # vertical-specific predicates (vertical strings here)
app/targeting/runtime.py             # register_targeting_runtime() — registers all predicates at startup
app/adapters/base.py                 # + SourceMeta.provides (capability declaration)
app/web/routes_buyer.py + templates  # composer UI, live estimate, save/list Segments
```

---

## 13. Buildable on current adapters vs needs new sources

- **Buildable NOW (OSM + fingerprint + website-enrich already stamp these):** category; geography
  (country/region/city/radius/postal/TLD/exclude-region); web-presence (has-site/reachable/ssl/
  online-ordering/booking/ecommerce/payments/last-verified); technographic over already-run
  fingerprints + the enrich intent signals; association-by-embedded-widget (token fingerprint);
  contactability (has phone/email, business-role-email derivation); exclusions
  (purchased/suppressed/opted-out/domain/TLD/score); freshness/confidence/source-type; opening-hours.
- **Needs ENRICH+ (same adapters, extended extraction):** arbitrary on-page keyword; page-type/careers
  (hiring proxy); outbound-link "links-to-entity"; OSM `brand`/`cuisine` capture; social-profile
  capture; running a **new** custom fingerprint over existing inventory (an enrichment pass).
- **Needs NEW LAWFUL SOURCE:** firmographic size/age/newly-registered (company-registry class); listed-
  in-directory / present-on-review-platform (entity-directory/review adapters); lifecycle intent
  (recently moved/expanding, job-board hiring) — each tagged with its source + lawful basis.
- **GATED / DEFERRED (not in this layer):** named decision-maker (personal) data — only via §10's gate.

---

## 14. Explicitly deferred

People-level/decision-maker data (gated, §10); new firmographic/registry/directory/review/job-board
adapters (each its own spec + lawful-basis review); a full crawler for page-type/keyword extraction
(ENRICH+ items ship incrementally); Segment sharing across buyers; scheduled Segment alerts ("notify
when N new leads match"); Segment-based exclusivity. The first build slice targets the **NOW** column +
the composition/Segment/estimate engine; ENRICH+/NEW-SOURCE filters land as their providers do.

---

## 15. Acceptance criteria (for the eventual build, not now)

1. Predicate registry + composition evaluator are generic; `app/core/` grep stays clean of vertical/
   source/entity/platform strings.
2. A composition of AND/OR/NOT predicates selects the correct candidate leads; the old coarse filters
   are expressible as a composition (back-compatible).
3. The builder offers ONLY predicates whose required attributes are populated in current inventory
   (data-driven), and renders entirely from the registry + `params_schema` (no hardcoded filter list).
4. Estimate returns count + score/freshness distributions + masked samples, recomputing on edit, with
   server-enforced masking identical to the marketplace.
5. A Segment can be named, saved, listed, re-estimated, and drive a search; Segments are buyer-owned.
6. Masking/suppression/opt-out/retention/audit are proven unchanged for Segment-matched leads at
   search, preview, unlock, and export.
7. No people-level data path exists; the gated future capability is documented but unbuilt.
```
