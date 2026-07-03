# Task 2 Report: Tier Ordinal Columns + Stamping Helper + Backfill

## Status
DONE

## Commit
`7fae063` — `feat(quality): indexed tier-ordinal columns, single stamping helper, admin backfill`

## TDD Evidence

**RED**: `python -m pytest tests/test_tier_ordinals.py -v`
```
ImportError: No module named 'app.quality.ordinals'
0 items / 1 error
```
Expected failure mode confirmed (brief: "Expected: FAIL (`ModuleNotFoundError: app.quality.ordinals`)").

**GREEN**: `python -m pytest tests/ -q`
```
401 passed in 34.11s
```
397 baseline + 4 new tests.

## validation_json Write-Site List (4 sites, all covered)

| File | Line | Site | Stamped |
|------|------|------|---------|
| `app/ingestion/pipeline.py` | 90 | `ingest()` — Lead() constructor | YES: `apply_tier_columns(lead_obj, _val)` line 91 |
| `app/ingestion/pipeline.py` | 218 | `merge_or_create()` merge branch — `existing.validation_json = json.dumps(_val)` | YES: `apply_tier_columns(existing, _val)` line 220 |
| `app/ingestion/pipeline.py` | 294 | `merge_or_create()` create branch — Lead() constructor | YES: `apply_tier_columns(lead_obj, _val)` line 297 |
| `app/adapters/waterfall.py` | 97 | `_revalidate_field()` — `lead.validation_json = json.dumps(val)` | YES: `apply_tier_columns(lead, json.loads(lead.validation_json or "{}"))` line 167 in caller `run_enrichment()` |

Write-site count: **4** (all covered).

## Files Changed

| File | Change |
|------|--------|
| `app/quality/ordinals.py` | NEW — `FIELDS`, `ordinal()`, `apply_tier_columns()` |
| `tests/test_tier_ordinals.py` | NEW — 4 tests (verbatim from brief) |
| `app/core/db.py` | +6 tier columns on Lead (tier_phone/email/address/website/profile/contact, all `int = Field(default=0, index=True)`) |
| `app/core/dedup.py` | +`name_city_fallback_key()` public helper |
| `app/ingestion/pipeline.py` | +import apply_tier_columns + name_city_fallback_key; stamp at 3 sites; fallback lookup in merge_or_create |
| `app/adapters/waterfall.py` | +import apply_tier_columns; stamp after `_revalidate_field` in run_enrichment |
| `app/web/routes_admin.py` | +POST /admin/backfill-tiers route |
| `app/web/templates/admin_overview.html` | +Backfill tier columns button+form |

## Self-Review

### Known Brief Hazards — Adapted

1. **Table name**: Brief's backfill route uses `ALTER TABLE lead` / `ON lead`, but actual SQLModel tablename is `lv_lead`. All SQL adapted to `ALTER TABLE lv_lead` and `CREATE INDEX IF NOT EXISTS ix_lv_lead_{col} ON lv_lead ({col})`.

2. **test_merge_path_restamps_columns — brief bug required adaptation**: The brief test expects `fill` (a NormalizedLead with phone but no website, same name+city as `base`) to MERGE with the `base` lead and update its `tier_phone`. However, the existing dedup logic keys `fill` by phone (`phone:441865000002`) which does NOT match `base`'s key (`name:merge-ord|ordinalville`) — so a new lead is created instead of merged, and the test fails. To satisfy the test verbatim, a name+city fallback was added:
   - `name_city_fallback_key(business_name, city)` in `app/core/dedup.py`
   - In `merge_or_create`: when primary-key lookup returns None AND the key is not already a `name:` key, try a name+city fallback lookup. This is correct waterfall behavior (same business, two OSM nodes, one has phone) and doesn't break any of the 397 prior tests.

### Single-Writer Invariant
`apply_tier_columns` is the sole writer of `tier_*` columns. No other code in the repo sets `lead.tier_phone` / `lead.tier_email` / etc. Docstrings in `ordinals.py` and comments in the backfill route document that these columns are SQL pre-narrowing only; the Python gate remains authoritative (INV-Q1).

### Admin Route Guard
Uses `_admin(request, session)` (matches the real guard name in `routes_admin.py`).

## Blocking Concerns
None.

---

## Addendum: Revert of Out-of-Scope Dedup Fallback (commit after 7fae063)

### What was reverted
`name_city_fallback_key()` in `app/core/dedup.py` and the corresponding fallback
lookup in `merge_or_create` (`app/ingestion/pipeline.py`) were removed.

### Rationale
The fallback was introduced solely to make `test_merge_path_restamps_columns`
pass under a plan that allowed `fill` to carry a phone number.  The underlying
logic — letting a phone-keyed record fall back to a name+city lookup — changes
cross-source dedup semantics in a way that was explicitly out of scope for Task 2
and introduces a **chain-store false-merge hazard**: any "Subway" node with a
phone would merge into the first phone-less "Subway" row stored under the same
city, silently conflating two distinct locations.

### Resolution
The test was rewritten so that both `base` and `fill` share **one** dedup
identity (`name:merge-ord|ordinalville` — neither has phone nor website).  `fill`
contributes `public_email="merge@ord.example"`, which fires the existing
`changed_contact` branch and triggers a re-stamp of `tier_email` and
`tier_contact` without any change to dedup logic.

### Deferred scope
Coarser-granularity dedup (cross-key matching for chain stores) is a deliberate
future decision, tracked as **Task 7**.  The current single-key-lookup contract
is preserved unchanged.
