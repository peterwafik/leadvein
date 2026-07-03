# Bulk OSM Ingestion via Geofabrik Extracts — Design

Date: 2026-07-03
Status: SPEC ONLY — user review gate before any build.
Branch: feature/bulk-osm (off feature/ux-overhaul; depends on its geo/quality layers).

## 0. Goal and honest framing

Raise raw inventory from hundreds toward hundreds of thousands by replacing city-by-city Overpass pulls with per-country Geofabrik PBF extracts, parsed locally. Volume comes from **more raw inventory**, never from a lower bar: "hot" still means gate-cleared (INV-Q1), and the ~63% of OSM businesses that publish no contact remain un-hot until a licensed contact source exists (deferred Signal Acquisition). Fingerprints stay the precision layer; bulk OSM is the breadth layer; cross-source dedup merges them as today.

**Current state this replaces (measured in code):** `app/adapters/osm.py` queries exactly 28 tag values (9 amenity, 12 shop, 2 leisure, 1 tourism + hardcoded map) via Overpass with `out center 100` per query and no retry/backoff; national coverage would need ~400 throttled city-pulls. The OSM wiki's own guidance: Overpass is for selections; country-scale extraction should use planet/Geofabrik extracts.

## 1. Geofabrik bulk pipeline

### 1.1 Source and files
- Download per-region PBF from `https://download.geofabrik.de/{region}-latest.osm.pbf` (e.g. `europe/great-britain`). Free, no key, no rate limit; ODbL. Region list is a small committed config (name → Geofabrik path → ISO country), extendable without code.
- Files cached under `var/pbf/{region}-latest.osm.pbf` with `If-Modified-Since` re-download guard (skip if fresh within 7 days). Streaming download with progress bytes. **Runbook honesty:** Great Britain ≈ 1.5–2.0 GB download; a full parse takes tens of minutes on a laptop; way-geometry resolution needs a node-location cache on disk (several GB, deleted after the run). Whole-planet is out of scope; per-country/region extracts are the unit.

### 1.2 Parser
- `pyosmium` (`osmium` on PyPI; maintained, C++-backed, streaming, Windows wheels). New dependency in requirements.txt.
- One streaming pass with a `SimpleHandler` over nodes and ways, `locations=True` with a **file-backed** node-location index (`sparse_file_array` in `var/`) so way centroids resolve without loading the country into RAM. Elements are matched against the tag config (§2); matches are normalized with the SAME field mapping as the existing OSM adapter (name, addr:*, phone/contact:phone, email, website, opening_hours, lat/lon or way centroid) — extracted into a shared `app/adapters/osm_common.py` used by both adapters so the mapping cannot drift.
- Nameless elements are skipped (business-entity rule: a POI without a name is not a marketable business record).

### 1.3 Import flow (reuses the existing pipeline contracts)
Batches of 500 normalized leads flow through the SAME steps as today, bulk-shaped:
1. **Dedup** — existing `dedupe_key` (domain → phone → name+city), checked in-batch and against the indexed column; existing merge/gap-fill semantics for cross-source hits (INV-14 unchanged). Re-running an import is idempotent (raw_ref `node/{id}` recorded; existing rows update `date_last_verified`).
2. **Compliance** — opt-out check per lead (as today); `country` from `addr:country` else derived from lat/lon via reverse lookup against the geo_ref reference (nearest-city assignment is v2; v1 stamps the extract's country code — honest and correct for country extracts). US-hold serve filter continues to apply to any US import.
3. **Validation stamp** — `build_validation` as today (pure function; phone format+line-type, email syntax + MX). At bulk scale MX is cached per unique domain for the run (unique domains ≪ leads). NEW: the same write path also stamps **tier ordinal columns** (§3.1).
4. **Score** — existing scoring profile.
5. **Store** — `add_all` + commit per batch. **No per-lead website enrichment during bulk** (300k network fetches would take days and hammer sites): the existing waterfall enrichment remains a separate, targeted pass an admin runs on subsets (e.g. gate-near leads in a campaign's geography). Stated in the admin UI so nobody expects bulk-imported leads to carry website-signal data on day one.
6. **Attribution/provenance** — `source_key=osm_geofabrik`, license ODbL, attribution "© OpenStreetMap contributors (ODbL) · extract by Geofabrik GmbH", per-field provenance as today; `retention_expiry` stamped as today.

### 1.4 Admin job UX (bulk imports are minutes-to-hours, not request/response)
- New "Bulk import" section on the admin Ingestion page: pick region (from config) → job starts in a **background thread**; the existing `IngestionJob` table becomes the progress record (`status`: downloading → parsing → importing → done/failed/cancelled; `counts_json` updated per batch: elements_seen, matched, new, merged, skipped_compliance, skipped_nameless, hot_so_far).
- Admin page polls the job row (simple fetch/refresh — no new SSE infra). Cancel button sets a flag checked between batches. One bulk job at a time (guard).
- Existing Overpass form stays for ad-hoc single-city pulls, labeled as such.

## 2. Tag taxonomy — configurable data, not code

Committed config `app/adapters/data/osm_business_tags.json`, loaded at seed into `CategoryMapping` rows (`source_key="osm"`, `external_value="shop=bakery"`, `category_key="bakery"`) — the table exists and is designed for exactly this; the bulk parser consults the DB-loaded mapping. Adding a business class later = config edit (or admin CategoryMapping row), zero code.

Config semantics, per OSM key:
- **`shop`: wildcard.** Every `shop=*` value maps to a category derived from the value (slugified; explicit alias map for the 24 existing taxonomy keys so current categories keep their names), MINUS an exclusion list (`vacant`, `no`, `mall` etc.).
- **`amenity`: allowlist** (~45 business-relevant values: restaurant, fast_food, cafe, bar, pub, pharmacy, bank, dentist, clinic, doctors, veterinary, fuel, car_wash, car_rental, driving_school, cinema, childcare, kindergarten, language_school, music_school, coworking_space, …). Amenity is mostly civic infrastructure — a wildcard would ingest benches and toilets; allowlist is the honest business filter.
- **`office`: wildcard** minus exclusions (`vacant`, `government` kept? — no: government offices excluded, not marketable B2B) → professional services: estate_agent, accountant, lawyer, it, insurance, architect, marketing, employment_agency, …
- **`craft`: wildcard** (trades: electrician, plumber, carpenter, builder, photographer, …).
- **`healthcare`: wildcard** minus exclusions.
- **`tourism`: allowlist** (hotel, guest_house, hostel, motel, apartment, camp_site).
- **`leisure`: allowlist** (fitness_centre, sports_centre, dance, bowling_alley, escape_game, …).

New categories auto-register in `LeadCategory` on first ingest (label = titleized key). The buyer UI's business-type control already populates from `LeadCategoryLink` — stays data-driven and honest with zero UI changes.

## 3. Scale: schema, indexes, and the SQL-first serve path

### 3.1 Tier ordinals — make the quality gate SQL-narrowable (INV-Q1 unchanged)
`build_validation` is a pure function of the lead row, so per-field tiers can be stamped as **indexed integer columns** at the same moment `validation_json` is written, by ONE shared helper (single writer → cannot drift; a test asserts column==json for random leads):
- New columns on Lead: `tier_phone`, `tier_email`, `tier_address`, `tier_website`, `tier_profile` (int ordinal of TIER_ORDER, 0–3, indexed), plus `tier_contact` = max(phone, email) for `business_contact` pushdown.
- A one-shot admin backfill command stamps existing rows.
- **INV-Q1 stays Python-authoritative:** the serve gate (`clears_gate` on the JSON) still runs on every served lead. The ordinals are a SQL *pre-narrowing* layer — an honest superset filter, never the final word. A property test asserts SQL-prefilter ∘ Python-gate ≡ Python-gate alone on randomized data.

### 3.2 Query path at 100k+ rows
- `matching_by_composition` gains: (a) pushdown for single-key nested OR groups (the shape `assemble_composition` emits for mixed geo) when every child pushes down; (b) quality-profile requirements pushed as `tier_x >= ordinal` clauses; (c) expiry pushed as `retention_expiry > now` (ISO strings compare correctly); (d) LIMIT-aware sampling so estimate never materializes 100k ORM rows to show 9 samples: count via SQL on the narrowed set, distributions via SQL GROUP BY on indexed `score_total`/`date_last_verified` bands, Python serve-filter re-check applied to the counted set via keyset pagination in batches (bounded memory), samples from the first gate-cleared page.
- Opt-out flips move to write time: when an opt-out is recorded, matching leads get `suppression_status='opted_out'` (indexed column already exists) — rare event, cheap update; serve-time Python check retained.
- New indexes: `region`, `retention_expiry`, and a composite `(country, score_total)`. `city`, `country`, `score_total`, `completeness_score`, `date_last_verified`, `dedupe_key`, `source_key`, `LeadCategoryLink.category_key` already indexed.
- SQLite pragmas at init: `journal_mode=WAL`, `synchronous=NORMAL` — required for bulk writes concurrent with reads.
- Acceptance target: p95 estimate < 1.0s and search page < 0.5s at 250k synthetic rows (benchmark test, slow-marked; revised 2026-07-03 from 0.5s/0.3s after measurement — the residual is the INV-Q1 Python-gate pass, an intrinsic honesty cost; sustained misses of the revised targets are a Postgres trigger per §3.3).

### 3.3 SQLite vs Postgres — YOUR DECISION (framed, not made)
| | SQLite + WAL + this spec's indexes | Postgres |
|---|---|---|
| UK national (~0.5M rows), single host, read-heavy | Comfortable; bulk import in WAL coexists with reads | Works, adds ops burden |
| Multiple countries (>1–2M rows) or concurrent bulk imports | Strains (single writer, file locking) | Designed for it |
| Full-text search, advanced JSON queries later | Limited | Native |
| Migration cost | — | Low-moderate: SQLModel models are portable; ISO-string dates portable; needs a data-copy script + connection config |

**Recommendation:** stay on SQLite for the UK national pilot (this spec makes it fast enough), and set the trigger now: second country OR concurrent-import need OR p95 targets missed ⇒ Postgres migration as its own small plan. Decide in review.

## 4. Honest volume projections — UK national pull (estimates, to be MEASURED after first import)

| Stage | Basis | Estimate |
|---|---|---|
| GB extract size | Geofabrik, changes weekly | ~1.5–2.0 GB PBF |
| Business-bearing named POIs (tag space in §2) | OSM GB tag counts; wide error bars | **~250k–500k raw candidates** |
| With any published contact (phone or email) | our measured city pulls: ~25–37% publish contact | ~70k–170k |
| **Hot (gate-cleared: validated contact, INV-Q1)** | ~90% of published contacts validate (format/MX) | **~60k–150k hot leads** |

So: **tens of thousands to low hundreds of thousands of hot leads nationally — not "every business now has a phone."** The ~63% contact-less majority is a data gap only a licensed contact source fills; bulk ingestion maximizes the free tier, nothing more. We will publish the real funnel numbers (raw → deduped → contact-present → gate-cleared) on the admin page after the first import, and the UI keeps showing only honest per-area counts. No gate loosening, ever.

## 4b. Admin bulk unlock & export (owner testing path) — USER ADDITION

Testing at national volume with per-lead credit unlocks is unworkable. Add an ADMIN-only bulk path, **strictly separated in code from the buyer unlock economy**, which stays fully intact for buyers:

- **Access:** admins may VIEW the buyer find/results pages (read-only browse of what buyers would see — same serve gate, same honest counts). Admin-only controls appear there: a select-all checkbox, per-card checkboxes, "Unlock selected", "Unlock all (N)", "Export selected", "Export all" (CSV + XLSX). Buyers never see these controls (test asserts absence for role=buyer).
- **Semantics:** admin bulk unlock spends NO credits, creates NO `PurchasedLead` rows, does NOT bump `times_sold`/`last_sold_at`, and touches NO `CreditTransaction` — it is an owner capability, not a purchase. It reveals full lead detail (server-side admin-guarded JSON) and enables export. Every bulk action writes ONE audit row (`admin.bulk_unlock` / `admin.bulk_export`) with lead count + composition hash.
- **Export content:** full unlocked detail per lead — business name, phone, email, website, category keys, address (line1/city/region/postcode/country), lat/lon, score + quality tier per field (phone/email/address/website), freshness date, source name + license + attribution, per-field provenance summary. CSV and XLSX (reuse the existing openpyxl export machinery); ODbL attribution embedded in the file (header/metadata row). Existing CSV formula-injection guard applies.
- **Honesty boundary unchanged:** the export contains only serveable leads (gate-cleared, not expired/opted-out/suppressed) — the admin path bypasses the *economy*, never the *compliance spine*. Code separation: new admin routes/module; the buyer `unlock_lead` path is untouched and its tests unmodified.

## 5. What does NOT change
Fingerprint discovery (precision layer, INV-11..15), Overpass adapter (ad-hoc city pulls), masking, quality gate authority (INV-Q1), suppression/opt-out/retention/audit on bulk leads exactly as today, grep-clean core + AST import boundary (`geofabrik`/`osmium` strings and imports stay OUT of app/core — new code lives in app/adapters + app/ingestion), buyer UI (taxonomy and coverage populate themselves from real data).

## 6. Testing (no huge downloads in the suite)
- **Committed fixture PBF** (a few KB, built once from hand-written OSM XML via osmium; both .osm source and .pbf committed): ~20 elements covering nodes + ways, each §2 tag class, contact/no-contact, nameless-skip, excluded-tag, duplicate pair.
- Tests: fixture parse → expected NormalizedLeads (field mapping, way centroid); tag-config mapping incl. wildcard/allowlist/exclusion + new-category auto-registration; idempotent re-import (no dupes, verified-date bump); tier-ordinal == validation_json consistency (property test); SQL-prefilter ≡ Python-gate equivalence (property test); WAL pragma set; grep/AST boundaries; job lifecycle (status transitions, cancel, counts) with a mocked parser; download cache guard with mocked HTTP.
- Benchmark (slow-marked): 250k synthetic rows → p95 targets.

## 7. Out of scope
Whole-planet imports; self-hosted Overpass; licensed contact sources (Signal Acquisition — separate, deferred); Postgres migration (decision here, work later if triggered); minute-level diff updates (re-import cadence is manual/weekly); payments (parked).
