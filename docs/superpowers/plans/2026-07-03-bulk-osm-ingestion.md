# Bulk OSM Ingestion (Geofabrik) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** National-scale lead inventory from Geofabrik per-country PBF extracts — streamed, tag-config-driven, gate-honest, fast at 100k+ rows — plus an admin bulk unlock/export testing path that never touches the buyer credit economy.

**Architecture:** A streaming PBF pipeline (`pyosmium` handler → tag-config matcher → shared OSM field mapping → batched `merge_or_create`) runs as a cancellable background job recorded on `IngestionJob`. Quality tiers are additionally stamped as indexed int columns by one shared helper, enabling SQL pre-narrowing of estimate/search while the Python gate stays authoritative (INV-Q1). Admin gets read access to the find page with bulk reveal/export actions in a separate module from the buyer unlock path.

**Tech Stack:** pyosmium (new dep), FastAPI/SQLModel/SQLite(WAL), openpyxl, existing pipeline contracts (`merge_or_create`, `dedupe_key`, `build_validation`).

**Spec:** `docs/superpowers/specs/2026-07-03-bulk-osm-ingestion-design.md` (SQLite pilot decision locked; Postgres trigger documented there).

## Global Constraints

- Business-entity data only: nameless OSM elements are SKIPPED.
- ODbL: attribution string for bulk leads is exactly `© OpenStreetMap contributors (ODbL) · extract by Geofabrik GmbH`; per-field provenance stamped as today; GeoNames footer rules unchanged.
- INV-Q1: Python gate remains the serve authority. Tier-ordinal SQL clauses are a PRE-NARROWING superset filter only; a property test must assert SQL∘Python ≡ Python alone.
- INV-Q2/Q6 untouched: no verified_live self-generation, no SMTP probing. `build_validation` stays the single validation authority.
- Grep-clean + AST boundary: strings `geofabrik`/`osmium` and imports of new modules must NOT appear in `app/core/**` (new code lives in app/adapters, app/ingestion, app/quality, app/web). The AST test (tests/test_core_import_boundary.py) must pass with NO new allowlist entries.
- Admin bulk unlock/export: NO credits spent, NO PurchasedLead rows, NO times_sold/last_sold_at changes, NO CreditTransaction. One audit row per bulk action. Buyer unlock path and its tests UNMODIFIED. Exports contain only serveable leads (gate-cleared, not expired/opted-out/suppressed).
- No huge downloads in the test suite: PBF parsing tested ONLY on the committed fixture (a few KB). Network happens in `scripts/` and the admin job, never in tests or seeds.
- Bulk import does NO per-lead website enrichment (`enrich_fn` is a no-op); stated in admin UI copy.
- Buyer-facing copy stays plain-language. Admin copy may name OSM/Geofabrik (it's the admin's tooling).
- Commands run from repo root; tests via `python -m pytest ... -q`. Suite baseline at branch start: **395 passed**.
- Commit after every task; append `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: pyosmium dependency, SQLite WAL pragmas, new indexes

**Files:**
- Modify: `requirements.txt`
- Modify: `app/core/db.py` (init_db pragmas + new indexes)
- Test: `tests/test_db_scale.py`

**Interfaces:**
- Produces: `init_db(url)` sets `journal_mode=WAL` and `synchronous=NORMAL` for SQLite engines via an `event.listens_for(engine, "connect")` hook. New Lead indexes: `region` (Field index), `retention_expiry` (Field index), composite `Index("ix_lv_lead_country_score", "country", "score_total")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_scale.py
"""Scale plumbing: WAL journal mode + indexes needed before a national import."""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlmodel import Session

import app.leadvault as lv


def test_sqlite_wal_enabled():
    with Session(lv.engine) as s:
        mode = s.exec(text("PRAGMA journal_mode")).one()[0]
        sync = s.exec(text("PRAGMA synchronous")).one()[0]
    assert str(mode).lower() == "wal"
    assert int(sync) == 1          # NORMAL


def test_scale_indexes_present():
    insp = inspect(lv.engine)
    names = {ix["name"] for ix in insp.get_indexes("lead")}
    assert any("region" in n for n in names)
    assert any("retention_expiry" in n for n in names)
    assert "ix_lv_lead_country_score" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db_scale.py -v`
Expected: FAIL (journal_mode "delete"; missing indexes)

- [ ] **Step 3: Implement**

In `requirements.txt` add:
```
osmium==4.0.2
```
(If pip resolution on Windows complains, use the latest 3.x/4.x with a Windows wheel — record the chosen pin in your report.)

In `app/core/db.py`:
- On the `Lead` model change `region: str = ""` → `region: str = Field(default="", index=True)` and `retention_expiry: str = ""` → `retention_expiry: str = Field(default="", index=True)`.
- In the Lead `__table_args__` (where `ix_lv_lead_source_key_col` lives) add: `Index("ix_lv_lead_country_score", "country", "score_total")`.
- In `init_db`, after engine creation and before `create_all`, add:

```python
    from sqlalchemy import event

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):   # pragma: no cover - exercised via test
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()
```

NOTE: SQLite `create_all` won't add columns/indexes to an EXISTING dev DB file. Tests use a fresh per-run DB (conftest) so they pass; for the dev DB, indexes on new columns appear after deleting leadvault.db OR running the Task 2 backfill command which also issues `CREATE INDEX IF NOT EXISTS`. Document this in your report; do not write a migration framework (YAGNI — SQLite pilot).

Run `pip install -r requirements.txt` and verify `python -c "import osmium; print(osmium.__version__)"`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_db_scale.py tests/ -q`
Expected: new tests PASS; full suite green (395 + 2)

- [ ] **Step 5: Commit**

```bash
git add requirements.txt app/core/db.py tests/test_db_scale.py
git commit -m "feat(scale): pyosmium dep, SQLite WAL pragmas, region/expiry/country-score indexes"
```

---

### Task 2: Tier ordinal columns + single stamping helper + backfill

**Files:**
- Create: `app/quality/ordinals.py`
- Modify: `app/core/db.py` (six int columns on Lead)
- Modify: `app/ingestion/pipeline.py` (stamp at every validation_json write: `ingest`, `merge_or_create` merge + create paths)
- Modify: `app/adapters/waterfall.py` (stamp after `_revalidate_field` updates validation_json)
- Modify: `app/web/routes_admin.py` (backfill POST route)
- Test: `tests/test_tier_ordinals.py`

**Interfaces:**
- Consumes: `TIER_ORDER` from app/quality/tiers.py; `validation_json` blobs from `build_validation`.
- Produces: `app.quality.ordinals.apply_tier_columns(lead, validation: dict) -> None` — writes `lead.tier_phone/tier_email/tier_address/tier_website/tier_profile` (int ordinal of the field's tier in TIER_ORDER, 0 when absent/missing) and `lead.tier_contact = max(tier_phone, tier_email)`. `ordinal(tier: str) -> int`. This helper is the ONLY writer of these columns.
- Produces: Lead columns `tier_phone, tier_email, tier_address, tier_website, tier_profile, tier_contact` — all `int = Field(default=0, index=True)`.
- Produces: `POST /admin/backfill-tiers` — admin-only; iterates all leads, re-derives ordinals from stored validation_json, also executes `CREATE INDEX IF NOT EXISTS` for the six tier indexes + Task-1 indexes (SQLite additive migration for existing dev DBs: it must first `ALTER TABLE lead ADD COLUMN` each missing tier column, wrapped in try/except for already-present); audits `admin.backfill_tiers` with count.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tier_ordinals.py
"""Tier ordinals: indexed int mirrors of validation_json tiers.

Single-writer rule: apply_tier_columns is the only code that writes tier_*
columns, and it is invoked at every site that writes validation_json — so the
columns can never drift from the JSON. INV-Q1 note: these columns are a SQL
PRE-NARROWING layer; the Python gate stays authoritative (tested in Task 10).
"""
from __future__ import annotations

import json

from sqlmodel import Session, select

import app.leadvault as lv
from app.adapters.base import NormalizedLead
from app.core.db import Lead
from app.ingestion.pipeline import ingest_normalized
from app.quality.ordinals import apply_tier_columns, ordinal
from app.quality.tiers import TIER_ORDER


def test_ordinal_maps_tier_order():
    assert ordinal("absent") == 0
    assert ordinal("present") == 1
    assert ordinal("validated") == 2
    assert ordinal("verified_live") == 3
    assert ordinal("bogus") == 0          # fail closed


def test_apply_tier_columns_mirrors_json():
    lead = Lead(business_name="T")
    val = {"phone": {"tier": "validated"}, "email": {"tier": "present"},
           "address": {"tier": "absent"}, "website": {"tier": "present"},
           "profile": {"tier": "validated"}, "freshness": {"tier": "validated"}}
    apply_tier_columns(lead, val)
    assert lead.tier_phone == 2 and lead.tier_email == 1
    assert lead.tier_address == 0 and lead.tier_website == 1
    assert lead.tier_profile == 2
    assert lead.tier_contact == 2          # max(phone, email)


def test_ingest_normalized_stamps_columns():
    n = NormalizedLead(
        business_name="Ordinal Bakery", category_keys=["bakery"],
        address={"city": "Ordinalville", "country": "GB"},
        phone="+441865000001", raw_ref="node/991")
    with Session(lv.engine) as s:
        ingest_normalized(s, [n], source_key="osm_geofabrik",
                          source_license="ODbL", enrich_fn=lambda _n: {})
        lead = s.exec(select(Lead).where(
            Lead.business_name == "Ordinal Bakery")).first()
        val = json.loads(lead.validation_json)
        assert lead.tier_phone == TIER_ORDER.index(val["phone"]["tier"])
        assert lead.tier_contact >= lead.tier_phone or lead.tier_contact >= lead.tier_email


def test_merge_path_restamps_columns():
    # gap-fill a contact onto an existing lead -> validation re-runs -> ordinals move
    base = NormalizedLead(business_name="Merge Ord", category_keys=["cafe"],
                          address={"city": "Ordinalville", "country": "GB"},
                          raw_ref="node/992")
    fill = NormalizedLead(business_name="Merge Ord", category_keys=["cafe"],
                          address={"city": "Ordinalville", "country": "GB"},
                          phone="+441865000002", raw_ref="node/993")
    with Session(lv.engine) as s:
        ingest_normalized(s, [base], source_key="osm_geofabrik",
                          source_license="ODbL", enrich_fn=lambda _n: {})
        lead = s.exec(select(Lead).where(Lead.business_name == "Merge Ord")).first()
        before = lead.tier_phone
        ingest_normalized(s, [fill], source_key="osm_geofabrik",
                          source_license="ODbL", enrich_fn=lambda _n: {})
        s.refresh(lead)
        assert before == 0 and lead.tier_phone >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tier_ordinals.py -v`
Expected: FAIL (`ModuleNotFoundError: app.quality.ordinals`)

- [ ] **Step 3: Implement `app/quality/ordinals.py`**

```python
"""Indexed int mirrors of per-field validation tiers.

apply_tier_columns is the ONLY writer of Lead.tier_* columns and must be
called at every site that writes validation_json — single writer, no drift.
The columns exist so estimate/search can PRE-NARROW candidates in SQL at
100k+ rows; the Python gate (clears_gate on the JSON) remains the serve
authority (INV-Q1)."""
from __future__ import annotations

from app.quality.tiers import TIER_ORDER

FIELDS = ("phone", "email", "address", "website", "profile")


def ordinal(tier: str) -> int:
    try:
        return TIER_ORDER.index(tier)
    except ValueError:
        return 0          # unknown tier fails closed


def apply_tier_columns(lead, validation: dict) -> None:
    for f in FIELDS:
        t = ((validation.get(f) or {}).get("tier")) or "absent"
        setattr(lead, f"tier_{f}", ordinal(t))
    lead.tier_contact = max(lead.tier_phone, lead.tier_email)
```

In `app/core/db.py` Lead model add (near completeness_score):

```python
    # Indexed int mirrors of per-field validation tiers (single writer:
    # the stamping helper in the validation pipeline). SQL pre-narrowing only.
    tier_phone: int = Field(default=0, index=True)
    tier_email: int = Field(default=0, index=True)
    tier_address: int = Field(default=0, index=True)
    tier_website: int = Field(default=0, index=True)
    tier_profile: int = Field(default=0, index=True)
    tier_contact: int = Field(default=0, index=True)
```
(Column names are generic ints — no quality-vocabulary strings; the grep + AST boundaries stay clean because db.py imports nothing new.)

In `app/ingestion/pipeline.py`: `from app.quality.ordinals import apply_tier_columns` and call `apply_tier_columns(lead_obj, _val)` immediately after each `validation_json=`/`completeness_score=` write — three sites: `ingest` (after Lead(...) construction, before session.add), `merge_or_create` merge branch (inside `if changed_contact:` after `existing.completeness_score = ...`), `merge_or_create` create branch (after Lead(...) construction).

In `app/adapters/waterfall.py`: after `_revalidate_field` writes the updated validation blob back to `lead.validation_json`, call `apply_tier_columns(lead, <the updated validation dict>)` (import at top).

In `app/web/routes_admin.py` add:

```python
@router.post("/backfill-tiers", dependencies=[Depends(csrf_protect)])
def backfill_tiers(request: Request, session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    import json as _json
    from sqlalchemy import text
    from app.core.db import Lead
    from app.quality.ordinals import apply_tier_columns, FIELDS
    # Additive SQLite migration for pre-existing dev DBs
    for col in [f"tier_{f}" for f in FIELDS] + ["tier_contact"]:
        try:
            session.exec(text(f"ALTER TABLE lead ADD COLUMN {col} INTEGER DEFAULT 0"))
        except Exception:
            pass          # column already exists
        session.exec(text(
            f"CREATE INDEX IF NOT EXISTS ix_lead_{col} ON lead ({col})"))
    n = 0
    for lead in session.exec(select(Lead)).all():
        apply_tier_columns(lead, _json.loads(lead.validation_json or "{}"))
        session.add(lead)
        n += 1
    session.commit()
    audit(session, u.id, "admin.backfill_tiers", "Lead", "all", {"count": n})
    return redirect("/admin")
```
Add a small "Backfill tier columns" button+form on `admin_overview.html` posting to it.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_tier_ordinals.py tests/test_quality_stamp.py tests/test_fingerprint_ingest_dedup.py tests/ -q`
Expected: green (397 + 4)

- [ ] **Step 5: Commit**

```bash
git add app/quality/ordinals.py app/core/db.py app/ingestion/pipeline.py app/adapters/waterfall.py app/web/routes_admin.py app/web/templates/admin_overview.html tests/test_tier_ordinals.py
git commit -m "feat(quality): indexed tier-ordinal columns, single stamping helper, admin backfill"
```

---

### Task 3: OSM business-tag config + matcher + CategoryMapping seed

**Files:**
- Create: `app/adapters/data/osm_business_tags.json`
- Create: `app/adapters/osm_tags.py`
- Modify: `app/leadvault.py` (seed call)
- Test: `tests/test_osm_tags.py`

**Interfaces:**
- Produces: `app.adapters.osm_tags.load_tag_config() -> dict` (parsed committed JSON); `match_categories(tags: dict, config=None) -> list[str]` (OSM element tags → taxonomy category keys, [] when no business match); `seed_osm_tag_mappings(session) -> int` (idempotent upsert into CategoryMapping: source_key="osm", external_value="{key}={value}" for allowlist/alias entries; wildcards resolved at match time, not enumerated); auto-registration: `ensure_category(session, key)` creates a LeadCategory row (label = key titleized) when a matched key is unknown — reuse `app/core/taxonomy.upsert_category` if its signature fits (check it; else call the taxonomy API that admin categories use).

**Config shape** (`osm_business_tags.json`):
```json
{
  "shop":       {"mode": "wildcard", "exclude": ["vacant", "no", "yes", "mall"],
                 "alias": {"bakery": "bakery", "hairdresser": "hair_salon", "beauty": "nail_salon",
                            "convenience": "convenience_store", "supermarket": "supermarket",
                            "laundry": "laundromat", "dry_cleaning": "dry_cleaner",
                            "butcher": "butcher", "florist": "florist", "clothes": "clothing_store",
                            "hardware": "hardware_store", "car_repair": "auto_repair"}},
  "amenity":    {"mode": "allowlist", "map": {"restaurant": "restaurant", "fast_food": "takeaway",
                 "cafe": "cafe", "bar": "bar", "pub": "pub", "pharmacy": "pharmacy",
                 "bank": "bank", "dentist": "dental_clinic", "clinic": "medical_clinic",
                 "doctors": "medical_clinic", "veterinary": "veterinary", "fuel": "fuel_station",
                 "car_wash": "car_wash", "car_rental": "car_rental", "driving_school": "driving_school",
                 "cinema": "cinema", "childcare": "childcare", "kindergarten": "nursery",
                 "language_school": "language_school", "music_school": "music_school",
                 "coworking_space": "coworking", "nightclub": "nightclub", "casino": "casino",
                 "ice_cream": "ice_cream", "food_court": "food_court", "internet_cafe": "internet_cafe",
                 "marketplace": "marketplace", "money_transfer": "money_transfer",
                 "bureau_de_change": "bureau_de_change", "post_office": "post_office",
                 "theatre": "theatre", "arts_centre": "arts_centre", "events_venue": "events_venue",
                 "conference_centre": "conference_centre", "exhibition_centre": "exhibition_centre",
                 "community_centre": "community_centre", "social_facility": "social_facility",
                 "animal_boarding": "animal_boarding", "animal_shelter": "animal_shelter",
                 "dive_centre": "dive_centre", "flight_school": "flight_school",
                 "gambling": "gambling", "studio": "studio", "vehicle_inspection": "vehicle_inspection",
                 "crematorium": "crematorium", "funeral_hall": "funeral_services"}},
  "office":     {"mode": "wildcard", "exclude": ["vacant", "government", "yes", "no"],
                 "alias": {"estate_agent": "real_estate", "accountant": "accountant",
                            "lawyer": "law_firm", "employment_agency": "recruitment",
                            "advertising_agency": "marketing_agency"}},
  "craft":      {"mode": "wildcard", "exclude": ["yes", "no"], "alias": {}},
  "healthcare": {"mode": "wildcard", "exclude": ["yes", "no"], "alias": {"dentist": "dental_clinic"}},
  "tourism":    {"mode": "allowlist", "map": {"hotel": "hotel", "guest_house": "guest_house",
                 "hostel": "hostel", "motel": "motel", "apartment": "holiday_apartment",
                 "camp_site": "camp_site"}},
  "leisure":    {"mode": "allowlist", "map": {"fitness_centre": "gym", "sports_centre": "sports_centre",
                 "dance": "dance_studio", "bowling_alley": "bowling_alley",
                 "escape_game": "escape_room", "amusement_arcade": "amusement_arcade",
                 "adult_gaming_centre": "gaming_centre", "miniature_golf": "miniature_golf",
                 "horse_riding": "horse_riding", "marina": "marina", "spa": "spa"}}
}
```
Wildcard semantics: category key = alias.get(value, slugified value) where slugify = lower + non-alnum→underscore; excluded values → no match. Precedence when an element carries multiple keys: first match in the order shop, amenity, office, craft, healthcare, tourism, leisure — collect ALL matches (a lead may carry several categories, as today).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_osm_tags.py
from __future__ import annotations

from sqlmodel import Session, select

import app.leadvault as lv
from app.adapters.osm_tags import load_tag_config, match_categories, seed_osm_tag_mappings
from app.core.db import LeadCategory


def test_allowlist_and_alias_mapping():
    assert match_categories({"amenity": "restaurant"}) == ["restaurant"]
    assert match_categories({"amenity": "fast_food"}) == ["takeaway"]
    assert match_categories({"shop": "hairdresser"}) == ["hair_salon"]


def test_wildcard_maps_unknown_values():
    assert match_categories({"shop": "fishing"}) == ["fishing"]
    assert match_categories({"craft": "electrician"}) == ["electrician"]
    assert match_categories({"office": "architect"}) == ["architect"]


def test_exclusions_and_non_business():
    assert match_categories({"shop": "vacant"}) == []
    assert match_categories({"office": "government"}) == []
    assert match_categories({"amenity": "bench"}) == []
    assert match_categories({"highway": "bus_stop"}) == []


def test_multi_tag_collects_all():
    cats = match_categories({"amenity": "cafe", "shop": "bakery"})
    assert set(cats) == {"cafe", "bakery"}


def test_seed_idempotent_and_registers_categories():
    with Session(lv.engine) as s:
        n1 = seed_osm_tag_mappings(s)
        n2 = seed_osm_tag_mappings(s)
        assert n2 == 0
        assert n1 >= 40          # allowlist+alias entries land in CategoryMapping
```

- [ ] **Step 2: Run — verify fails** (`ModuleNotFoundError`)

- [ ] **Step 3: Implement `app/adapters/osm_tags.py`**

```python
"""OSM business-tag taxonomy — CONFIG, not code (spec §2).

The committed JSON defines which OSM tags are business-bearing and how they
map to taxonomy category keys. Wildcard keys (shop/office/craft/healthcare)
derive categories from tag values minus exclusions; allowlist keys
(amenity/tourism/leisure) map only curated business values. Adding a business
class later = config edit, zero code."""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "data", "osm_business_tags.json")
_KEY_ORDER = ("shop", "amenity", "office", "craft", "healthcare", "tourism", "leisure")


@lru_cache(maxsize=1)
def load_tag_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")


def match_categories(tags: dict, config: dict | None = None) -> list[str]:
    config = config or load_tag_config()
    out: list[str] = []
    for key in _KEY_ORDER:
        rule = config.get(key)
        value = (tags or {}).get(key)
        if not rule or not value:
            continue
        if rule["mode"] == "allowlist":
            cat = rule["map"].get(value)
        else:  # wildcard
            if value in rule.get("exclude", []):
                cat = None
            else:
                cat = rule.get("alias", {}).get(value) or _slug(value)
        if cat and cat not in out:
            out.append(cat)
    return out


def seed_osm_tag_mappings(session) -> int:
    """Idempotent upsert of explicit (allowlist + alias) entries into
    CategoryMapping (source_key='osm'). Wildcards resolve at match time and
    are not enumerated. Also registers each mapped category in LeadCategory."""
    from sqlmodel import select
    from app.core.db import CategoryMapping
    from app.core.taxonomy import upsert_category

    config = load_tag_config()
    n = 0
    for key in _KEY_ORDER:
        rule = config.get(key) or {}
        entries = rule.get("map", {}) if rule.get("mode") == "allowlist" else rule.get("alias", {})
        for value, cat in entries.items():
            ext = f"{key}={value}"
            exists = session.exec(select(CategoryMapping).where(
                CategoryMapping.source_key == "osm",
                CategoryMapping.external_value == ext)).first()
            if exists:
                continue
            session.add(CategoryMapping(source_key="osm", external_value=ext,
                                        category_key=cat))
            upsert_category(session, cat, cat.replace("_", " ").title())
            n += 1
    session.commit()
    return n
```
CHECK `app/core/taxonomy.upsert_category`'s real signature before use (explorer says lines 27–43); adapt the call if it differs (e.g. takes label only, or session-first). If `CategoryMapping` fields differ from (source_key, external_value, category_key), read app/core/db.py and adapt — do not invent columns.

In `app/leadvault.py` `_seed_accounts()` after `seed_geo_fixture(s)`:
```python
        from app.adapters.osm_tags import seed_osm_tag_mappings
        seed_osm_tag_mappings(s)
```

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_osm_tags.py tests/ -q` → green

- [ ] **Step 5: Commit**

```bash
git add app/adapters/data/osm_business_tags.json app/adapters/osm_tags.py app/leadvault.py tests/test_osm_tags.py
git commit -m "feat(osm): configurable business-tag taxonomy (wildcards+allowlists) seeded into CategoryMapping"
```

---

### Task 4: Shared OSM field mapping (`osm_common`) + refactor Overpass adapter onto it

**Files:**
- Create: `app/adapters/osm_common.py`
- Modify: `app/adapters/osm.py` (normalize delegates to osm_common; tag matching switches to osm_tags.match_categories)
- Test: `tests/test_osm_common.py` (+ existing `tests/test_osm_adapter.py` must stay green)

**Interfaces:**
- Produces: `normalized_from_tags(tags: dict, *, lat, lon, raw_ref: str, categories: list[str], source_key: str) -> NormalizedLead | None` — returns None when `tags.get("name")` is falsy (business-entity rule); maps addr:housenumber+addr:street→line1, addr:city/state/postcode/country, phone or contact:phone, email or contact:email, website or contact:website, opening_hours, attributes `{"open_7_days": bool}` (same derivation as current osm.py).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_osm_common.py
from __future__ import annotations

from app.adapters.osm_common import normalized_from_tags


def _tags(**kw):
    base = {"name": "Common Cafe", "amenity": "cafe", "addr:city": "Oxford",
            "addr:street": "High St", "addr:housenumber": "12",
            "addr:postcode": "OX1 1AA", "addr:country": "GB",
            "contact:phone": "+44 1865 000000", "website": "https://commoncafe.example",
            "opening_hours": "Mo-Su 08:00-18:00"}
    base.update(kw)
    return base


def test_full_mapping():
    n = normalized_from_tags(_tags(), lat=51.75, lon=-1.25, raw_ref="node/1",
                             categories=["cafe"], source_key="osm_geofabrik")
    assert n.business_name == "Common Cafe"
    assert n.address == {"line1": "12 High St", "city": "Oxford", "region": "",
                         "postal_code": "OX1 1AA", "country": "GB",
                         "lat": 51.75, "lon": -1.25}
    assert n.phone == "+44 1865 000000"
    assert n.website_url == "https://commoncafe.example"
    assert n.attributes.get("open_7_days") is True
    assert n.raw_ref == "node/1"


def test_nameless_skipped():
    assert normalized_from_tags(_tags(name=""), lat=0, lon=0, raw_ref="node/2",
                                categories=["cafe"], source_key="x") is None


def test_contact_prefixed_fallbacks():
    t = _tags()
    del t["website"]
    t["contact:website"] = "https://alt.example"
    t["email"] = "hi@commoncafe.example"
    n = normalized_from_tags(t, lat=0, lon=0, raw_ref="way/3",
                             categories=["cafe"], source_key="x")
    assert n.website_url == "https://alt.example"
    assert n.public_email == "hi@commoncafe.example"
```

- [ ] **Step 2: Run — FAIL** (module missing)

- [ ] **Step 3: Implement**

Write `app/adapters/osm_common.py` by EXTRACTING the field-mapping logic from `app/adapters/osm.py:59-90` (read it first; keep the exact fallback order and the `open_7_days` derivation, e.g. opening_hours contains "Mo-Su" or equivalent — preserve whatever osm.py does today):

```python
"""Shared OSM tags -> NormalizedLead mapping.

Single source of truth used by BOTH the Overpass adapter (ad-hoc city pulls)
and the bulk PBF importer, so the field mapping cannot drift between them."""
from __future__ import annotations

from app.adapters.base import NormalizedLead


def normalized_from_tags(tags: dict, *, lat, lon, raw_ref: str,
                         categories: list[str], source_key: str) -> NormalizedLead | None:
    name = (tags or {}).get("name") or ""
    if not name:
        return None          # business-entity rule: nameless POIs are not leads
    house = tags.get("addr:housenumber", "")
    street = tags.get("addr:street", "")
    line1 = " ".join(x for x in (house, street) if x)
    opening = tags.get("opening_hours", "") or ""
    return NormalizedLead(
        business_name=name,
        category_keys=list(categories or []),
        address={"line1": line1, "city": tags.get("addr:city", ""),
                 "region": tags.get("addr:state", ""),
                 "postal_code": tags.get("addr:postcode", ""),
                 "country": tags.get("addr:country", ""),
                 "lat": lat, "lon": lon},
        phone=tags.get("phone") or tags.get("contact:phone", "") or "",
        public_email=tags.get("email") or tags.get("contact:email", "") or "",
        website_url=tags.get("website") or tags.get("contact:website", "") or "",
        opening_hours=opening,
        attributes={"open_7_days": ("Mo-Su" in opening or "24/7" in opening)},
        source_key=source_key,
        raw_ref=raw_ref,
    )
```
(Before finalizing, compare with osm.py's actual `open_7_days` logic and copy ITS exact expression so behavior is identical.)

Refactor `app/adapters/osm.py` `normalize()` to: derive categories via `app.adapters.osm_tags.match_categories(tags)` (replacing `_OSM_TO_CATEGORY` lookups — the config's allowlist covers the old 28 values; verify each old value maps identically, extend the config alias maps if any old key differs), resolve lat/lon incl. `center` fallback as today, then delegate to `normalized_from_tags(..., source_key=self.meta.key)`. Existing `tests/test_osm_adapter.py` MUST pass unmodified — if an assertion breaks, your config/extraction diverged from current behavior; fix the config/code, not the test.

- [ ] **Step 4: Run** — `python -m pytest tests/test_osm_common.py tests/test_osm_adapter.py tests/ -q` → green

- [ ] **Step 5: Commit**

```bash
git add app/adapters/osm_common.py app/adapters/osm.py tests/test_osm_common.py
git commit -m "refactor(osm): shared tags->NormalizedLead mapping; Overpass adapter on tag config"
```

---

### Task 5: Fixture PBF + streaming parser

**Files:**
- Create: `tests/fixtures/bulk_fixture.osm` (hand-written XML source, committed)
- Create: `tests/fixtures/bulk_fixture.osm.pbf` (built once, committed binary)
- Create: `scripts/build_pbf_fixture.py`
- Create: `app/ingestion/pbf_stream.py`
- Test: `tests/test_pbf_stream.py`

**Interfaces:**
- Produces: `app.ingestion.pbf_stream.stream_business_leads(pbf_path: str, *, source_key: str, node_cache_path: str | None = None, progress_cb=None) -> Iterator[NormalizedLead]` — streams nodes AND ways; for ways, location resolution via osmium's file-backed index when `node_cache_path` given, else in-memory `flex_mem` (fixture-sized default); way lat/lon = centroid of node locations (average is fine); calls `progress_cb(elements_seen: int)` every 10_000 elements when provided; skips non-business (no tag-config match) and nameless elements.
- Produces: fixture with EXACTLY these 12 elements (IDs and expected outcomes below are the test contract):
  - node 101: name="Fixture Bakery", shop=bakery, addr:city=Testville, phone=+441865111111 → lead, category bakery
  - node 102: name="Fixture Electrician", craft=electrician, email=sparks@fixture.example → lead, category electrician (wildcard)
  - node 103: name="Fixture Office", office=architect → lead, category architect
  - node 104: shop=bakery (NO name) → skipped (nameless)
  - node 105: name="Fixture Bench", amenity=bench → skipped (non-business)
  - node 106: name="Vacant Shop", shop=vacant → skipped (excluded)
  - node 107: name="Fixture Hotel", tourism=hotel, website=https://hotel.fixture.example → lead
  - node 108: name="Fixture GP", healthcare=doctor → lead (wildcard healthcare)
  - nodes 201,202,203,204: bare location nodes for the way (no tags)
  - way 301 (refs 201-204, closed): name="Fixture Supermarket", shop=supermarket, addr:city=Testville → lead with centroid lat/lon
  - node 109: name="Fixture Dup Bakery", shop=bakery, phone=+441865111111 → lead (same phone as 101 — dedup exercised at IMPORT stage, Task 6, not here)
  Total expected from parser: **7 leads** (101,102,103,107,108,109 + way 301).

- [ ] **Step 1: Write `scripts/build_pbf_fixture.py` and the .osm XML**

The XML (`tests/fixtures/bulk_fixture.osm`) — write all 12 elements with lat/lon around (51.75, -1.25); ways reference the bare nodes. Then:

```python
# scripts/build_pbf_fixture.py
"""One-time fixture builder: .osm XML -> .osm.pbf via pyosmium. Run manually;
the committed .pbf is what tests consume (no osmium tooling needed at test time)."""
from __future__ import annotations

import os
import sys

import osmium

SRC = os.path.join("tests", "fixtures", "bulk_fixture.osm")
DST = os.path.join("tests", "fixtures", "bulk_fixture.osm.pbf")


def main() -> None:
    if os.path.exists(DST):
        os.remove(DST)
    writer = osmium.SimpleWriter(DST)
    try:
        for obj in osmium.FileProcessor(SRC):
            if obj.is_node():
                writer.add_node(obj)
            elif obj.is_way():
                writer.add_way(obj)
            elif obj.is_relation():
                writer.add_relation(obj)
    finally:
        writer.close()
    print(f"wrote {DST} ({os.path.getsize(DST)} bytes)")


if __name__ == "__main__":
    sys.exit(main())
```
(If the installed pyosmium version lacks `FileProcessor`, use the `osmium.SimpleHandler`+`osmium.SimpleWriter` copy pattern from its docs — the goal is only XML→PBF. Record what worked.) Run it; commit BOTH files.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_pbf_stream.py
from __future__ import annotations

import os

from app.ingestion.pbf_stream import stream_business_leads

FIXTURE = os.path.join("tests", "fixtures", "bulk_fixture.osm.pbf")


def test_fixture_parses_expected_leads():
    leads = list(stream_business_leads(FIXTURE, source_key="osm_geofabrik"))
    by_name = {l.business_name: l for l in leads}
    assert len(leads) == 7
    assert by_name["Fixture Bakery"].category_keys == ["bakery"]
    assert by_name["Fixture Bakery"].phone == "+441865111111"
    assert by_name["Fixture Electrician"].category_keys == ["electrician"]
    assert by_name["Fixture Hotel"].website_url == "https://hotel.fixture.example"
    assert "Fixture Bench" not in by_name          # non-business skipped
    assert "Vacant Shop" not in by_name            # excluded skipped


def test_way_gets_centroid_and_raw_ref():
    leads = {l.business_name: l for l in
             stream_business_leads(FIXTURE, source_key="osm_geofabrik")}
    sm = leads["Fixture Supermarket"]
    assert sm.raw_ref.startswith("way/")
    assert sm.address["lat"] is not None and sm.address["lon"] is not None
    assert 51.0 < sm.address["lat"] < 52.5


def test_progress_callback_fires():
    seen = []
    list(stream_business_leads(FIXTURE, source_key="x",
                               progress_cb=lambda n: seen.append(n)))
    # fixture is tiny; the final flush call must still report the total
    assert seen and seen[-1] >= 12
```

- [ ] **Step 3: Run — FAIL**, then implement `app/ingestion/pbf_stream.py`

```python
"""Streaming PBF -> NormalizedLead. Memory-bounded: elements are handled one
at a time; way locations resolve via an osmium node-location index (file-backed
for country extracts, in-memory for fixtures). Whole-planet is out of scope."""
from __future__ import annotations

from typing import Iterator

import osmium

from app.adapters.osm_common import normalized_from_tags
from app.adapters.osm_tags import match_categories

_PROGRESS_EVERY = 10_000


class _Collector(osmium.SimpleHandler):
    def __init__(self, source_key: str, progress_cb=None):
        super().__init__()
        self.source_key = source_key
        self.progress_cb = progress_cb
        self.elements_seen = 0
        self.out: list = []

    def _tick(self):
        self.elements_seen += 1
        if self.progress_cb and self.elements_seen % _PROGRESS_EVERY == 0:
            self.progress_cb(self.elements_seen)

    def _handle(self, tags: dict, lat, lon, raw_ref: str):
        cats = match_categories(tags)
        if not cats:
            return
        n = normalized_from_tags(tags, lat=lat, lon=lon, raw_ref=raw_ref,
                                 categories=cats, source_key=self.source_key)
        if n is not None:
            self.out.append(n)

    def node(self, n):
        self._tick()
        tags = dict(n.tags)
        self._handle(tags, n.location.lat, n.location.lon, f"node/{n.id}")

    def way(self, w):
        self._tick()
        tags = dict(w.tags)
        if not tags:
            return
        lats, lons = [], []
        for nd in w.nodes:
            try:
                if nd.location.valid():
                    lats.append(nd.location.lat)
                    lons.append(nd.location.lon)
            except osmium.InvalidLocationError:
                continue
        lat = sum(lats) / len(lats) if lats else None
        lon = sum(lons) / len(lons) if lons else None
        self._handle(tags, lat, lon, f"way/{w.id}")


def stream_business_leads(pbf_path: str, *, source_key: str,
                          node_cache_path: str | None = None,
                          progress_cb=None) -> Iterator[NormalizedLead]:
    handler = _Collector(source_key, progress_cb)
    if node_cache_path:
        idx = f"sparse_file_array,{node_cache_path}"
    else:
        idx = "flex_mem"
    handler.apply_file(pbf_path, locations=True, idx=idx)
    if progress_cb:
        progress_cb(handler.elements_seen)
    yield from handler.out
```
NOTE for the implementer: `_Collector` buffers matches (business POIs are a small fraction of elements — a country yields low hundreds of thousands of small dataclasses, acceptable). If pyosmium's API differs on your pinned version (e.g. `InvalidLocationError` name, `location.valid()`), adapt to the real API and document. Add the missing `NormalizedLead` import.

- [ ] **Step 4: Run** — `python -m pytest tests/test_pbf_stream.py tests/ -q` → green

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/bulk_fixture.osm tests/fixtures/bulk_fixture.osm.pbf scripts/build_pbf_fixture.py app/ingestion/pbf_stream.py tests/test_pbf_stream.py
git commit -m "feat(bulk): streaming PBF parser + committed fixture extract"
```

---

### Task 6: Geofabrik region source (download, cache, attribution)

**Files:**
- Create: `app/adapters/geofabrik.py`
- Modify: `app/adapters/providers/__init__.py` (register)
- Test: `tests/test_geofabrik.py`

**Interfaces:**
- Produces: `REGIONS: dict[str, dict]` — committed region config: `{"great-britain": {"path": "europe/great-britain", "country": "GB", "label": "United Kingdom"}, "monaco": {"path": "europe/monaco", "country": "MC", "label": "Monaco (tiny — live test region)"}, "ireland-and-northern-ireland": {"path": "europe/ireland-and-northern-ireland", "country": "IE", "label": "Ireland + NI"}}` (extendable data).
- Produces: `download_extract(region_key: str, *, dest_dir: str = "var/pbf", http_get=None, max_age_days: int = 7) -> str` — returns local path; skips download when the cached file is younger than max_age_days; injectable `http_get(url, dest_path)` for tests (default: streaming requests download writing chunks + printing/logging progress).
- Produces: `SourceMeta(key="osm_geofabrik", name="OpenStreetMap (Geofabrik extract)", type="open_data", url="https://download.geofabrik.de", license="ODbL", key_env="")` + `attribution() -> "© OpenStreetMap contributors (ODbL) · extract by Geofabrik GmbH"` (module-level object with .meta and .attribution() registered in the adapter registry so it appears on the admin Sources page; it is NOT a discover/normalize adapter — bulk import drives it. Give it no-op `discover`/`normalize` raising `NotImplementedError("bulk import only")` so registry typing holds).

- [ ] **Step 1: Failing test**

```python
# tests/test_geofabrik.py
from __future__ import annotations

import os
import time

from app.adapters.geofabrik import REGIONS, download_extract, GEOFABRIK


def test_regions_config_shape():
    assert "great-britain" in REGIONS and "monaco" in REGIONS
    for r in REGIONS.values():
        assert set(r) >= {"path", "country", "label"}


def test_download_uses_cache_when_fresh(tmp_path):
    calls = []
    def fake_get(url, dest):
        calls.append(url)
        with open(dest, "wb") as f:
            f.write(b"pbf-bytes")
    p1 = download_extract("monaco", dest_dir=str(tmp_path), http_get=fake_get)
    p2 = download_extract("monaco", dest_dir=str(tmp_path), http_get=fake_get)
    assert p1 == p2 and os.path.exists(p1)
    assert len(calls) == 1                      # second call hit the cache
    assert "europe/monaco-latest.osm.pbf" in calls[0]


def test_stale_cache_redownloads(tmp_path):
    calls = []
    def fake_get(url, dest):
        calls.append(url)
        with open(dest, "wb") as f:
            f.write(b"pbf")
    p = download_extract("monaco", dest_dir=str(tmp_path), http_get=fake_get)
    old = time.time() - 8 * 86400
    os.utime(p, (old, old))
    download_extract("monaco", dest_dir=str(tmp_path), http_get=fake_get)
    assert len(calls) == 2


def test_attribution_and_meta():
    assert GEOFABRIK.meta.key == "osm_geofabrik"
    assert GEOFABRIK.meta.license == "ODbL"
    assert "OpenStreetMap contributors" in GEOFABRIK.attribution()
    assert "Geofabrik" in GEOFABRIK.attribution()
```

- [ ] **Step 2: Run — FAIL**, then implement `app/adapters/geofabrik.py`

```python
"""Geofabrik per-region OSM extracts — the bulk volume source (spec §1).

Free, ODbL, no key, no rate limit. One streaming download per region, cached
under var/pbf with a freshness window. RUNBOOK HONESTY: Great Britain is
~1.5-2.0 GB and parsing takes tens of minutes; per-country extracts are the
unit — whole-planet is out of scope."""
from __future__ import annotations

import os
import time

import requests

from app.adapters.base import SourceMeta

BASE = "https://download.geofabrik.de"

REGIONS: dict[str, dict] = {
    "great-britain": {"path": "europe/great-britain", "country": "GB",
                       "label": "United Kingdom (Great Britain)"},
    "ireland-and-northern-ireland": {"path": "europe/ireland-and-northern-ireland",
                                     "country": "IE", "label": "Ireland + Northern Ireland"},
    "monaco": {"path": "europe/monaco", "country": "MC",
                "label": "Monaco (tiny - live test region)"},
}


def _default_get(url: str, dest: str) -> None:
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        tmp = dest + ".part"
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        os.replace(tmp, dest)


def download_extract(region_key: str, *, dest_dir: str = os.path.join("var", "pbf"),
                     http_get=None, max_age_days: int = 7) -> str:
    region = REGIONS[region_key]
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"{region_key}-latest.osm.pbf")
    if os.path.exists(dest):
        age_days = (time.time() - os.path.getmtime(dest)) / 86400
        if age_days < max_age_days:
            return dest
    url = f"{BASE}/{region['path']}-latest.osm.pbf"
    (http_get or _default_get)(url, dest)
    return dest


class _Geofabrik:
    meta = SourceMeta(key="osm_geofabrik", name="OpenStreetMap (Geofabrik extract)",
                      type="open_data", url=BASE, license="ODbL", key_env="")

    def attribution(self) -> str:
        return "© OpenStreetMap contributors (ODbL) · extract by Geofabrik GmbH"

    def discover(self, query):          # bulk import drives this source
        raise NotImplementedError("bulk import only")

    def normalize(self, raw):
        raise NotImplementedError("bulk import only")


GEOFABRIK = _Geofabrik()
```
Register in `app/adapters/providers/__init__.py` `register_providers()`: `from app.adapters.geofabrik import GEOFABRIK` + `registry.register(GEOFABRIK)` (read the file first and follow its exact pattern).

- [ ] **Step 3: Run** — `python -m pytest tests/test_geofabrik.py tests/ -q` → green
- [ ] **Step 4: Commit**

```bash
git add app/adapters/geofabrik.py app/adapters/providers/__init__.py tests/test_geofabrik.py
git commit -m "feat(bulk): Geofabrik region source - cached streaming download, ODbL attribution, registry entry"
```

---

### Task 7: Bulk import driver (batched, cancellable, MX-cached, funnel counts)

**Files:**
- Create: `app/ingestion/bulk.py`
- Modify: `app/ingestion/pipeline.py` (thread optional `mx_lookup` through `merge_or_create` + `ingest_normalized` into `build_validation` calls — default None preserves behavior)
- Test: `tests/test_bulk_import.py`

**Interfaces:**
- Consumes: `stream_business_leads` (T5), `download_extract`/`REGIONS`/`GEOFABRIK` (T6), `merge_or_create` (+ new `mx_lookup` kwarg), `dedupe_key`, `is_opted_out`, `IngestionJob`, `invalidate_geo_counts`, `recompute_coverage`, `sync_lead_categories`.
- Produces: `run_bulk_import(session, region_key: str, *, scoring_profile_key: str = "", pbf_path: str | None = None, batch_size: int = 500, cancel_check=None, on_progress=None) -> dict` — counts dict `{"elements_seen", "matched", "stored_new", "merged", "skipped_compliance", "skipped_duplicate_in_run", "hot"}`. `pbf_path` override lets tests/the fixture path skip download. `cancel_check()` truthy between batches → stop cleanly, status "cancelled" left to the caller. `on_progress(counts)` after each batch. "hot" = stored leads with `tier_contact >= ordinal("validated")` (measured funnel honesty, spec §4).
- MX caching: a per-run `functools.lru_cache`-style dict wrapper around the default MX lookup, passed as `mx_lookup` so `build_validation` hits DNS once per unique domain.
- In-run dedup: track dedupe_keys seen this run; second occurrence SKIPS (counted `skipped_duplicate_in_run`) rather than merging into the just-created row twice (matches existing `ingest` semantics).
- NO enrichment: `enrich_fn=lambda n: {}` equivalents; country default: `NormalizedLead.address["country"]` when present else the region's configured country code (spec §1.3.2) — set via `country_override`.
- Commit per batch; `sync_lead_categories` for NEW leads (merge path leaves categories as-is per merge_or_create semantics); after the run: `recompute_coverage(session)` + `invalidate_geo_counts()` + one `IngestionJob`-style audit (`audit(session, actor, "bulk_ingest", "IngestionJob", str(job_id_or_region), counts)` — job row handling itself is Task 8's).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bulk_import.py
"""Bulk import over the committed fixture PBF — full pipeline contracts hold."""
from __future__ import annotations

import json
import os

from sqlmodel import Session, select

import app.leadvault as lv
from app.core.db import Lead
from app.ingestion.bulk import run_bulk_import
from app.quality.ordinals import ordinal

FIXTURE = os.path.join("tests", "fixtures", "bulk_fixture.osm.pbf")


def _run(s, **kw):
    return run_bulk_import(s, "monaco", pbf_path=FIXTURE, **kw)


def test_fixture_import_counts_and_rows():
    with Session(lv.engine) as s:
        counts = _run(s)
        assert counts["matched"] == 7
        assert counts["stored_new"] + counts["merged"] + counts["skipped_duplicate_in_run"] == 7
        lead = s.exec(select(Lead).where(Lead.business_name == "Fixture Bakery")).first()
        assert lead is not None
        assert lead.source_key == "osm_geofabrik"
        assert lead.source_license == "ODbL"
        assert "OpenStreetMap contributors" in lead.attribution
        assert lead.country == "GB"            # addr:country wins over region default
        prov = json.loads(lead.field_provenance_json or "{}")
        assert prov.get("phone", {}).get("source") == "osm_geofabrik"
        assert lead.tier_contact >= ordinal("present")
        # hot funnel counted honestly
        assert counts["hot"] <= counts["stored_new"] + counts["merged"]


def test_region_country_fallback():
    with Session(lv.engine) as s:
        _run(s)
        gp = s.exec(select(Lead).where(Lead.business_name == "Fixture GP")).first()
        # fixture GP has no addr:country -> falls back to region country (MC)
        assert gp.country == "MC"


def test_reimport_is_idempotent():
    with Session(lv.engine) as s:
        _run(s)
        n_before = len(s.exec(select(Lead).where(
            Lead.source_key == "osm_geofabrik")).all())
        counts2 = _run(s)
        n_after = len(s.exec(select(Lead).where(
            Lead.source_key == "osm_geofabrik")).all())
        assert n_after == n_before                 # no duplicates
        assert counts2["merged"] >= 1              # existing rows matched


def test_cancel_stops_between_batches():
    with Session(lv.engine) as s:
        counts = _run(s, batch_size=2, cancel_check=lambda: True)
        # cancelled before the first batch commit completes the run
        assert counts["matched"] <= 7


def test_dedup_within_run():
    # Fixture Dup Bakery shares a phone with Fixture Bakery -> same dedupe key
    with Session(lv.engine) as s:
        counts = _run(s)
        assert counts["skipped_duplicate_in_run"] >= 1 or counts["merged"] >= 1
```
NOTE: tests share the per-process DB — names are fixture-unique so cross-test state is tolerable; assertions use relative/≥ forms where prior tests may have imported already.

- [ ] **Step 2: Run — FAIL**, then implement.

`app/ingestion/pipeline.py` changes: add `mx_lookup=None` kwarg to `merge_or_create(...)` and `ingest_normalized(...)`; thread into every `build_validation({...})` call as `build_validation({...}, mx_lookup=mx_lookup)`. Default None keeps today's `_default_mx` behavior (build_validation already handles `mx_lookup or _default_mx`).

`app/ingestion/bulk.py`:

```python
"""Bulk import driver: Geofabrik PBF -> batched pipeline (spec §1.3).

Reuses the SAME contracts as every other source: dedupe_key, opt-out check,
build_validation (single validation authority), scoring, per-field provenance
via merge_or_create. Deliberately NO per-lead website enrichment (a national
run would mean 300k network fetches) — enrichment stays a separate targeted
admin pass. MX lookups are cached per unique domain for the run."""
from __future__ import annotations

from app.adapters.geofabrik import GEOFABRIK, REGIONS, download_extract
from app.core.compliance import audit, host_of, is_opted_out
from app.core.dedup import dedupe_key
from app.core.targeting.coverage import recompute_coverage
from app.geo.coverage import invalidate_geo_counts
from app.ingestion.pbf_stream import stream_business_leads
from app.ingestion.pipeline import merge_or_create
from app.quality.ordinals import ordinal
from app.quality.validators.email import _default_mx


def _cached_mx():
    cache: dict[str, bool] = {}
    def lookup(domain: str) -> bool:
        if domain not in cache:
            cache[domain] = _default_mx(domain)
        return cache[domain]
    return lookup


def run_bulk_import(session, region_key: str, *, scoring_profile_key: str = "",
                    pbf_path: str | None = None, batch_size: int = 500,
                    cancel_check=None, on_progress=None,
                    actor_user_id=None) -> dict:
    region = REGIONS[region_key]
    counts = {"elements_seen": 0, "matched": 0, "stored_new": 0, "merged": 0,
              "skipped_compliance": 0, "skipped_duplicate_in_run": 0, "hot": 0}

    path = pbf_path or download_extract(region_key)
    mx = _cached_mx()
    seen_keys: set[str] = set()
    batch: list = []

    def _progress(n_elements: int) -> None:
        counts["elements_seen"] = n_elements

    def _flush() -> None:
        from app.core.leadcats import sync_lead_categories
        for n in batch:
            domain = host_of(n.website_url)
            if is_opted_out(session, domain=domain, phone=n.phone,
                            email=n.public_email):
                counts["skipped_compliance"] += 1
                continue
            existed_before = True
            lead = merge_or_create(
                session, n,
                source_key=GEOFABRIK.meta.key,
                license=GEOFABRIK.meta.license,
                scoring_profile_key=scoring_profile_key,
                attribution=GEOFABRIK.attribution(),
                source_name=GEOFABRIK.meta.name,
                source_url=GEOFABRIK.meta.url,
                enrichment={},
                country_override=region["country"],
                mx_lookup=mx,
            )
            if lead.times_sold == 0 and lead.date_discovered == lead.date_last_verified:
                existed_before = False          # heuristic replaced below
            # authoritative new-vs-merged: id assigned in this flush
            if lead.id is None or lead in session.new:
                counts["stored_new"] += 1
                session.flush()
                sync_lead_categories(session, lead)
            else:
                counts["merged"] += 1
            if lead.tier_contact >= ordinal("validated"):
                counts["hot"] += 1
        session.commit()
        batch.clear()
        if on_progress:
            on_progress(dict(counts))

    node_cache = None
    if pbf_path is None:          # real extract: file-backed node index
        import os
        node_cache = os.path.join("var", "pbf", f"{region_key}-nodes.cache")

    for n in stream_business_leads(path, source_key=GEOFABRIK.meta.key,
                                   node_cache_path=node_cache,
                                   progress_cb=_progress):
        if cancel_check and cancel_check():
            break
        counts["matched"] += 1
        key = dedupe_key(n)
        if key in seen_keys:
            counts["skipped_duplicate_in_run"] += 1
            continue
        seen_keys.add(key)
        batch.append(n)
        if len(batch) >= batch_size:
            _flush()
    if batch and not (cancel_check and cancel_check()):
        _flush()

    recompute_coverage(session)
    invalidate_geo_counts()
    audit(session, actor_user_id, "bulk_ingest", "IngestionJob", region_key, counts)
    session.commit()
    # cleanup node cache file
    if node_cache:
        import os
        try:
            os.remove(node_cache)
        except OSError:
            pass
    return counts
```
IMPLEMENTER NOTE on new-vs-merged detection: the sketch above shows the intent but the `session.new` check must be verified against SQLModel/SQLAlchemy semantics — the clean way: check `find_existing(session, key)` BEFORE calling merge_or_create (one extra indexed query per lead; acceptable) and count new/merged from that. Use the clean way; delete the heuristic lines. Also verify `_default_mx`'s exact name/signature in app/quality/validators/email.py and adapt (it may take the domain or the full email — read it).

- [ ] **Step 3: Run** — `python -m pytest tests/test_bulk_import.py tests/test_tier_ordinals.py tests/ -q` → green

- [ ] **Step 4: Commit**

```bash
git add app/ingestion/bulk.py app/ingestion/pipeline.py tests/test_bulk_import.py
git commit -m "feat(bulk): batched cancellable import driver - dedup, opt-out, MX cache, honest funnel counts"
```

---

### Task 8: Background job + admin Bulk-import UI (progress, cancel, funnel display)

**Files:**
- Create: `app/web/bulk_jobs.py`
- Modify: `app/web/routes_admin.py` (start/status/cancel routes)
- Modify: `app/web/templates/admin_ingest.html` (Bulk import section)
- Test: `tests/test_bulk_job_routes.py`

**Interfaces:**
- Produces: `app.web.bulk_jobs.start_bulk_job(engine, region_key, scoring_profile_key, actor_user_id, run_fn=None) -> int` — refuses (raises `RuntimeError`) when a job is already running; creates an `IngestionJob` row (`adapter_key="osm_geofabrik"`, `query_json={"region": region_key}`, `status="running"`, counts_json="{}"), spawns a daemon `threading.Thread` that opens its OWN `Session(engine)`, calls `run_fn or run_bulk_import` with `cancel_check` reading a module-level cancel flag and `on_progress` writing counts_json via a short-lived session, then sets status `done`/`cancelled`/`failed` (+ `error` key inside counts_json on exception). `request_cancel(job_id)`, `active_job(session) -> IngestionJob | None`.
- Produces routes (all admin-guarded): `POST /admin/bulk-import` (form: region, scoring_profile_key) → starts, redirects to /admin/ingest; `GET /admin/bulk-import/status` → JSON `{job_id, status, counts}` of the latest job; `POST /admin/bulk-import/cancel` → sets flag, redirects.
- Produces UI: "Bulk import (Geofabrik extract)" card on admin_ingest.html — region `<select>` from REGIONS labels, honest copy: "Downloads the full country extract (Great Britain ≈ 1.5–2 GB) and imports every business-bearing OSM element. Takes minutes for small regions, tens of minutes for a country. No per-lead website enrichment during bulk — run enrichment separately on subsets. Funnel counts below are measured, not promised."; live status block (JS fetch poll of /status every 3s while status=running) showing elements_seen / matched / stored_new / merged / skipped / **hot so far**; Cancel button.

- [ ] **Step 1: Failing test**

```python
# tests/test_bulk_job_routes.py
from __future__ import annotations

import json
import re
import time

from fastapi.testclient import TestClient
from sqlmodel import Session, select

import app.leadvault as lv
from app.core.db import IngestionJob


def _admin_client():
    c = TestClient(lv.app)
    m = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text)
    token = m.group(1)
    c.post("/login", data={"email": "admin@demo.local", "password": "admin12345",
                           "csrf_token": token}, follow_redirects=False)
    return c, token


def _fake_run(session, region_key, **kw):
    on_progress = kw.get("on_progress")
    counts = {"elements_seen": 12, "matched": 7, "stored_new": 7, "merged": 0,
              "skipped_compliance": 0, "skipped_duplicate_in_run": 0, "hot": 3}
    if on_progress:
        on_progress(counts)
    return counts


def test_bulk_job_lifecycle(monkeypatch):
    import app.web.bulk_jobs as bj
    monkeypatch.setattr(bj, "run_bulk_import", _fake_run)
    c, token = _admin_client()
    r = c.post("/admin/bulk-import", data={"csrf_token": token, "region": "monaco",
                                           "scoring_profile_key": ""},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    for _ in range(50):                       # wait for the thread
        body = c.get("/admin/bulk-import/status").json()
        if body["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert body["status"] == "done"
    assert body["counts"]["hot"] == 3
    with Session(lv.engine) as s:
        job = s.exec(select(IngestionJob).where(
            IngestionJob.adapter_key == "osm_geofabrik")).all()[-1]
        assert job.status == "done"
        assert json.loads(job.counts_json)["matched"] == 7


def test_second_job_refused_while_running(monkeypatch):
    import app.web.bulk_jobs as bj
    started = {"go": False}
    def slow_run(session, region_key, **kw):
        while not started["go"]:
            time.sleep(0.02)
            if kw.get("cancel_check") and kw["cancel_check"]():
                return {"matched": 0}
        return {"matched": 0}
    monkeypatch.setattr(bj, "run_bulk_import", slow_run)
    c, token = _admin_client()
    c.post("/admin/bulk-import", data={"csrf_token": token, "region": "monaco",
                                       "scoring_profile_key": ""},
           follow_redirects=False)
    r2 = c.post("/admin/bulk-import", data={"csrf_token": token, "region": "monaco",
                                            "scoring_profile_key": ""},
                follow_redirects=False)
    # second start while running -> redirect back with no new job thread
    c.post("/admin/bulk-import/cancel", data={"csrf_token": token},
           follow_redirects=False)
    started["go"] = True
    assert r2.status_code in (302, 303, 409)


def test_bulk_import_requires_admin():
    c = TestClient(lv.app)
    m = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text)
    token = m.group(1)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": token}, follow_redirects=False)
    r = c.post("/admin/bulk-import", data={"csrf_token": token, "region": "monaco"},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/login" in r.headers.get("location", "/login")
```
(Admin creds exist in the test DB only if seeded — check conftest/app seeding; if `admin@demo.local` isn't seeded under tests, create the admin user in the test via `create_user` exactly as tests/test_audiences.py created a second buyer.)

- [ ] **Step 2: Run — FAIL**, then implement `app/web/bulk_jobs.py`:

```python
"""One-at-a-time background bulk-import job (thread + IngestionJob row).

The web request only starts/polls/cancels; the thread owns its own Session.
Progress is durable (counts_json on the job row) so a page reload never loses
the funnel numbers."""
from __future__ import annotations

import json
import threading

from sqlmodel import Session, select

from app.core.db import IngestionJob
from app.ingestion.bulk import run_bulk_import

_lock = threading.Lock()
_state = {"thread": None, "job_id": None, "cancel": False}


def active_job(session) -> IngestionJob | None:
    job = session.exec(select(IngestionJob)
                       .where(IngestionJob.adapter_key == "osm_geofabrik")
                       .order_by(IngestionJob.id.desc())).first()
    return job


def request_cancel(job_id: int | None = None) -> None:
    _state["cancel"] = True


def start_bulk_job(engine, region_key: str, scoring_profile_key: str,
                   actor_user_id, run_fn=None) -> int:
    with _lock:
        t = _state["thread"]
        if t is not None and t.is_alive():
            raise RuntimeError("a bulk import is already running")
        with Session(engine) as s:
            job = IngestionJob(adapter_key="osm_geofabrik",
                               query_json=json.dumps({"region": region_key}),
                               status="running", counts_json="{}")
            s.add(job)
            s.commit()
            s.refresh(job)
            job_id = job.id
        _state["cancel"] = False
        _state["job_id"] = job_id

        def _work():
            fn = run_fn or run_bulk_import
            def _write(status: str, counts: dict):
                with Session(engine) as ws:
                    row = ws.get(IngestionJob, job_id)
                    row.status = status
                    row.counts_json = json.dumps(counts)
                    ws.add(row)
                    ws.commit()
            try:
                with Session(engine) as ws:
                    counts = fn(ws, region_key,
                                scoring_profile_key=scoring_profile_key,
                                cancel_check=lambda: _state["cancel"],
                                on_progress=lambda c: _write("running", c),
                                actor_user_id=actor_user_id)
                _write("cancelled" if _state["cancel"] else "done", counts)
            except Exception as exc:              # noqa: BLE001 - job boundary
                _write("failed", {"error": str(exc)})

        th = threading.Thread(target=_work, daemon=True)
        _state["thread"] = th
        th.start()
        return job_id
```
Routes in routes_admin.py (follow the file's guard/csrf patterns): start (catch RuntimeError → redirect with `?bulk=busy`), status (JSON from `active_job`), cancel. `run_fn` stays injectable — the tests monkeypatch `bulk_jobs.run_bulk_import`, so call it via the module attribute (`fn = run_fn or run_bulk_import` must resolve at call time: use `fn = run_fn or globals()["run_bulk_import"]`? NO — simplest: `import app.web.bulk_jobs as _self; fn = run_fn or _self.run_bulk_import` or reference the module-level name inside `_work` without rebinding; verify the monkeypatch actually takes effect and adjust).
Template: add the card + poll JS per the interface block (plain fetch, no framework; stop polling when status != running; render funnel counts incl. "hot so far").

- [ ] **Step 3: Run** — `python -m pytest tests/test_bulk_job_routes.py tests/ -q` → green
- [ ] **Step 4: Commit**

```bash
git add app/web/bulk_jobs.py app/web/routes_admin.py app/web/templates/admin_ingest.html tests/test_bulk_job_routes.py
git commit -m "feat(bulk): background one-at-a-time import job with durable progress, cancel, honest funnel display"
```

---

### Task 9: Composition pushdown upgrades (OR-groups, extra clauses, expiry)

**Files:**
- Modify: `app/core/targeting/composition.py`
- Modify: `app/core/targeting/estimate.py`
- Test: `tests/test_pushdown_scale.py`

**Interfaces:**
- Produces: `_pushdown_clauses` handles nested `{"op": "OR", "nodes": [...]}` children of the top-level AND: when EVERY child of the OR is a non-negated predicate whose `sql_pushdown` returns a clause, emit `sqlalchemy.or_(*child_clauses)`; otherwise skip the group (Python still evaluates it — superset stays honest).
- Produces: `matching_by_composition(session, composition, *, exclude_lead_ids=frozenset(), extra_clauses=None)` — appends `extra_clauses` (list of SQLAlchemy clauses) to the WHERE. Callers pass gate clauses via ctx (Task 10).
- Produces: `estimate(...)` pushes expiry into SQL — build `now = datetime.now(timezone.utc).isoformat()` and pass `Lead.retention_expiry > now` as an extra clause (retention strings are ISO — verify against app/core/retention.py `is_expired`/`expiry_for` formats first; keep the Python `is_expired` check too, superset rule).
- INVARIANT: pure-Python evaluation result must be IDENTICAL with and without pushdown (property test below).

- [ ] **Step 1: Failing test**

```python
# tests/test_pushdown_scale.py
"""Pushdown upgrades: OR-groups + extra clauses narrow in SQL; results are
provably identical to pure-Python evaluation (superset honesty)."""
from __future__ import annotations

import json

from sqlmodel import Session, select

import app.leadvault as lv
from app.core.db import Lead
from app.core.targeting.composition import (_pushdown_clauses,
                                            matching_by_composition, selects)
from app.core.targeting.view import lead_view


def _mk(city, country, score):
    return Lead(business_name=f"P-{city}-{score}", city=city, country=country,
                score_total=score, category_keys_json="[]",
                validation_json=json.dumps({"profile": {"tier": "validated"},
                                            "phone": {"tier": "validated"}}))


def _seed(s):
    for city, cc, sc in [("Pushtown", "GB", 90), ("Pushville", "GB", 40),
                          ("Pushberg", "DE", 90)]:
        s.add(_mk(city, cc, sc))
    s.commit()


OR_GEO = {"op": "AND", "nodes": [
    {"op": "OR", "nodes": [
        {"predicate": "geo.country_any", "params": {"in": ["DE"]}},
        {"predicate": "geo.city_any", "params": {"in": ["Pushtown"]}}]},
    {"predicate": "quality.min_score", "params": {"min": 50}}]}


def test_or_group_pushdown_emits_clause():
    with Session(lv.engine) as s:
        clauses = _pushdown_clauses(s, OR_GEO)
    assert clauses and len(clauses) == 2      # or_(...) + min_score


def test_pushdown_equals_pure_python():
    with Session(lv.engine) as s:
        _seed(s)
        pushed = {l.id for l in matching_by_composition(s, OR_GEO)}
        pure = {l.id for l in s.exec(select(Lead)).all()
                if selects(lead_view(l), OR_GEO)}
        assert pushed == pure


def test_or_group_with_unpushable_child_falls_back():
    comp = {"op": "AND", "nodes": [
        {"op": "OR", "nodes": [
            {"predicate": "geo.city_any", "params": {"in": ["Pushtown"]}},
            {"predicate": "web.has_signal", "params": {"signal": "x"}}]}]}
    with Session(lv.engine) as s:
        _seed(s)
        clauses = _pushdown_clauses(s, comp)
        # OR group skipped (has_signal has no pushdown) -> no clause for it
        assert not clauses
        pushed = {l.id for l in matching_by_composition(s, comp)}
        pure = {l.id for l in s.exec(select(Lead)).all()
                if selects(lead_view(l), comp)}
        assert pushed == pure


def test_extra_clauses_narrow():
    with Session(lv.engine) as s:
        _seed(s)
        rows = matching_by_composition(
            s, {"op": "AND", "nodes": []},
            extra_clauses=[Lead.score_total >= 90])
        assert rows and all(l.score_total >= 90 for l in rows)
```

- [ ] **Step 2: Run — FAIL**, then implement in composition.py:

```python
def _node_clause(session, node):
    if "op" in node or node.get("negate"):
        return None
    pred = registry.get(node["predicate"])
    fn = getattr(pred, "sql_pushdown", None)
    return fn(session, node.get("params", {})) if fn is not None else None


def _pushdown_clauses(session, composition):
    if composition.get("op") != "AND":
        return None
    from sqlalchemy import or_
    clauses = []
    for node in composition.get("nodes", []):
        if node.get("op") == "OR":
            children = node.get("nodes", [])
            child_clauses = [_node_clause(session, c) for c in children]
            if children and all(c is not None for c in child_clauses):
                clauses.append(or_(*child_clauses))
            continue
        clause = _node_clause(session, node)
        if clause is not None:
            clauses.append(clause)
    return clauses


def matching_by_composition(session, composition, *, exclude_lead_ids=frozenset(),
                            extra_clauses=None):
    clauses = list(_pushdown_clauses(session, composition) or [])
    clauses.extend(extra_clauses or [])
    if clauses:
        candidates = session.exec(select(Lead).where(*clauses)).all()
    else:
        candidates = session.exec(select(Lead)).all()
    out = []
    for lead in candidates:
        if lead.id in exclude_lead_ids:
            continue
        if selects(lead_view(lead), composition):
            out.append(lead)
    return out
```
estimate.py: read `app/core/retention.py` first to confirm the ISO format; then in `estimate()` compute `now_iso` and call `matching_by_composition(session, composition, extra_clauses=[Lead.retention_expiry > now_iso])` (import Lead there) — Python `is_expired` check STAYS (superset rule; also covers empty-string expiries: verify `"" > now_iso` is False in SQL string comparison — empty strings sort BEFORE, so leads with empty expiry would be EXCLUDED wrongly; guard with `or_(Lead.retention_expiry == "", Lead.retention_expiry > now_iso)`).

- [ ] **Step 3: Run** — `python -m pytest tests/test_pushdown_scale.py tests/test_targeting_eval.py tests/test_targeting_estimate.py tests/ -q` → green
- [ ] **Step 4: Commit**

```bash
git add app/core/targeting/composition.py app/core/targeting/estimate.py tests/test_pushdown_scale.py
git commit -m "feat(targeting): OR-group pushdown, extra WHERE clauses, expiry pushdown - Python-equivalence tested"
```

---

### Task 10: SQL gate clauses + estimate fast path + benchmark

**Files:**
- Create: `app/quality/sql_gate.py`
- Modify: `app/web/routes_buyer.py` (`run_estimate` builds ctx["sql_clauses"])
- Modify: `app/core/targeting/estimate.py` (uses ctx["sql_clauses"] as extra_clauses)
- Test: `tests/test_sql_gate.py`, `tests/test_estimate_benchmark.py` (slow-marked)

**Interfaces:**
- Produces: `app.quality.sql_gate.profile_clauses(profile) -> list | None` — for each `(field, required_tier)` in `profile.required`: field in {phone,email,address,website,profile} → `Lead.tier_{field} >= ordinal(required_tier)`; `business_contact` → `Lead.tier_contact >= ordinal(required_tier)`; ANY other field (e.g. verified_live-requiring fields still map by ordinal — that's fine; truly unknown field names) → return None (no SQL narrowing; Python gate alone). Quality imports core — allowed direction.
- Produces: `run_estimate` (routes_buyer.py): after combining profiles, `ctx = {"quality_profile": prof, "sql_clauses": profile_clauses(prof) or []}`. estimate() passes `ctx.get("sql_clauses")` into matching_by_composition's extra_clauses (core reads an opaque list from ctx — no quality import in core).
- CRITICAL INVARIANT (INV-Q1): the Python serve gate still runs on every lead in estimate's visible-filter loop — SQL clauses only narrow. Property test: for randomized leads and each registered profile, `estimate` results with sql_clauses == results with the clauses stripped.
- Benchmark: `tests/test_estimate_benchmark.py` marked `@pytest.mark.slow` (register the marker in pytest.ini) — seeds 250k synthetic leads ONCE into a dedicated throwaway sqlite file (NOT the shared test DB; build engine directly), then asserts p95 of 20 estimate calls (country+category+profile composition) < 0.5s and search-page-shaped call < 0.3s. Excluded from default runs via `addopts = -m "not slow"`? — NO: changing addopts would skip nothing else; instead the marker alone + document `python -m pytest -m slow tests/test_estimate_benchmark.py` in the test docstring; default `pytest tests/` will still collect it — so guard with `pytest.importorskip`-style env check: skip unless `RUN_SCALE_BENCH=1`.

- [ ] **Step 1: Failing test**

```python
# tests/test_sql_gate.py
from __future__ import annotations

import json
import random

from sqlmodel import Session

import app.leadvault as lv
from app.core.db import Lead
from app.core.targeting.estimate import estimate
from app.quality.ordinals import apply_tier_columns
from app.quality.profiles.registry import all_keys, get as get_profile
from app.quality.sql_gate import profile_clauses


def test_clauses_for_registered_profiles():
    for key in all_keys():
        clauses = profile_clauses(get_profile(key))
        assert clauses is not None            # all registered profiles are tier-expressible
        assert len(clauses) == len(get_profile(key).required)


def test_unknown_field_returns_none():
    from app.quality.profiles.base import QualityProfile
    weird = QualityProfile(key="w", label="w", required={"attributes.size_band": "validated"})
    assert profile_clauses(weird) is None


def _random_lead(i):
    tiers = ["absent", "present", "validated"]
    val = {f: {"tier": random.choice(tiers)}
           for f in ("phone", "email", "address", "website", "profile")}
    lead = Lead(business_name=f"SG-{i}", city="Gateville", country="GB",
                score_total=random.randint(0, 100),
                validation_json=json.dumps(val),
                retention_expiry="2999-01-01T00:00:00+00:00")
    apply_tier_columns(lead, val)
    return lead


def test_sql_narrowing_equals_python_gate():          # INV-Q1 superset proof
    random.seed(42)
    with Session(lv.engine) as s:
        for i in range(120):
            s.add(_random_lead(i))
        s.commit()
        comp = {"op": "AND", "nodes": [
            {"predicate": "geo.city_any", "params": {"in": ["Gateville"]}}]}
        for key in all_keys():
            prof = get_profile(key)
            with_sql = estimate(s, 1, comp, ctx={
                "quality_profile": prof,
                "sql_clauses": profile_clauses(prof) or []})
            without_sql = estimate(s, 1, comp, ctx={"quality_profile": prof})
            assert with_sql["count"] == without_sql["count"], key
            assert with_sql["score_distribution"] == without_sql["score_distribution"], key
```

- [ ] **Step 2: Run — FAIL**, then implement.

`app/quality/sql_gate.py`:

```python
"""SQL pre-narrowing clauses for quality profiles (spec §3).

Superset filter ONLY: the Python gate (clears_gate) remains the serve
authority on every lead (INV-Q1). Returns None when a profile requires a
field the tier columns don't cover — callers then skip SQL narrowing."""
from __future__ import annotations

from app.core.db import Lead
from app.quality.ordinals import FIELDS, ordinal


def profile_clauses(profile) -> list | None:
    clauses = []
    for field_, tier in (profile.required or {}).items():
        if field_ == "business_contact":
            clauses.append(Lead.tier_contact >= ordinal(tier))
        elif field_ in FIELDS:
            clauses.append(getattr(Lead, f"tier_{field_}") >= ordinal(tier))
        else:
            return None
    return clauses
```
estimate.py: `extra = list((ctx or {}).get("sql_clauses") or [])` merged with the expiry clause from Task 9 before calling matching_by_composition.
routes_buyer.py `run_estimate`: after `combine_profiles`, `from app.quality.sql_gate import profile_clauses` and set `ctx = {"quality_profile": prof, "sql_clauses": profile_clauses(prof) or []}`.

`tests/test_estimate_benchmark.py` — write per the interface block (env-gated skip; dedicated engine via `create_engine("sqlite:///<tmp>")` + `SQLModel.metadata.create_all`; seed with `apply_tier_columns`; time with `time.perf_counter`; document honest results in the report). Register `markers = slow: scale benchmarks (RUN_SCALE_BENCH=1)` in pytest.ini.

- [ ] **Step 3: Run** — `python -m pytest tests/test_sql_gate.py tests/ -q` green; then `RUN_SCALE_BENCH=1 python -m pytest tests/test_estimate_benchmark.py -v -s` and PASTE the measured p95 numbers into your report (if targets miss, report DONE_WITH_CONCERNS with the numbers — do NOT weaken the assertion silently).
- [ ] **Step 4: Commit**

```bash
git add app/quality/sql_gate.py app/core/targeting/estimate.py app/web/routes_buyer.py tests/test_sql_gate.py tests/test_estimate_benchmark.py pytest.ini
git commit -m "feat(scale): SQL gate pre-narrowing wired into estimate (Python gate stays authoritative) + 250k benchmark"
```

---

### Task 11: Admin bulk unlock & export (economy-bypassing, compliance-intact)

**Files:**
- Create: `app/web/routes_admin_bulk.py`
- Modify: `app/leadvault.py` (include router)
- Modify: `app/web/routes_find.py` (`_buyer` guard on find/audiences pages ONLY gains admin read access: rename usage to `_viewer` allowing role in ("buyer","admin") for GET find/estimate/geo pages; POST save/unlock/compile stay buyer-scoped? NO — compile/estimate are needed for admin browsing: allow admin on compile/estimate too; `find_save` stays buyer-only (admins don't own audiences); template gains admin-only bulk controls)
- Modify: `app/web/templates/find.html` (admin-only selection checkboxes + bulk action bar; `window._isAdmin`)
- Modify: `app/engine/export.py` (add `rows_to_xlsx(cols, rows) -> bytes` if absent — read the file first)
- Test: `tests/test_admin_bulk_export.py`

**Interfaces:**
- Produces: `POST /admin/bulk/reveal` (csrf JSON, admin-only) — body `{"lead_ids": [...]}` (≤500) → full `unlock_view`+quality rows for SERVEABLE leads only (each id re-checked: exists, not expired, not opted-out, passes serve filters); audits ONE row `admin.bulk_unlock {"count": n}`.
- Produces: `POST /admin/bulk/export` (csrf form, admin-only) — fields: `format` (`csv`|`xlsx`), and either `lead_ids` (comma-joined) or `composition` (JSON; server re-runs matching + serve filters — "Export all" sends the composition, never 10k ids). Streams a download (`Content-Disposition: attachment; filename=leadvault-export.{ext}`). Columns: EXPORT_COLUMNS from app/core/export_leads.py PLUS `latitude, longitude, tier_phone_label, tier_email_label, tier_address_label, tier_website_label, provenance_summary` (labels = TIER_ORDER names; provenance_summary = "field:source" comma-joined). First data row of CSV/XLSX metadata: attribution line `© OpenStreetMap contributors (ODbL) · includes Geofabrik-extract data` when any exported row has source_key=osm_geofabrik, else the distinct source attributions — simplest honest form: a leading comment row with `", ".join(sorted({r.attribution for rows}))`. Formula-injection guard: reuse whatever `rows_to_csv` already does (verify it does; if the guard lives elsewhere, apply the same escaping to XLSX cell values).
- Produces: economy separation (tested): NO PurchasedLead rows, NO CreditTransaction rows, `times_sold` unchanged after reveal+export.
- Produces: find-page admin affordances — when `user.role == "admin"`: checkbox on each result card, "Select all", action bar "Unlock selected (n)" (calls /admin/bulk/reveal, swaps cards to full detail: name, phone, email, website), "Export selected" + "Export all (N)" (form-posts /admin/bulk/export with ids or current composition). Buyers see NONE of this (server-side `{% if user.role == 'admin' %}` — test asserts the strings absent for buyers).

- [ ] **Step 1: Failing test**

```python
# tests/test_admin_bulk_export.py
"""Admin bulk unlock/export: bypasses the ECONOMY, never the COMPLIANCE spine."""
from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient
from sqlmodel import Session, select

import app.leadvault as lv
from app.core.db import CreditTransaction, Lead, PurchasedLead
from app.quality.ordinals import apply_tier_columns


def _login(c, email, pw):
    m = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text)
    token = m.group(1)
    c.post("/login", data={"email": email, "password": pw, "csrf_token": token},
           follow_redirects=False)
    return token


def _seed_lead(s, name="Bulk Exportable"):
    val = {"profile": {"tier": "validated"}, "phone": {"tier": "validated"},
           "email": {"tier": "present"}, "address": {"tier": "present"},
           "website": {"tier": "absent"}}
    lead = Lead(business_name=name, city="Exportville", country="GB",
                phone="+441865222222", score_total=80,
                category_keys_json='["bakery"]',
                validation_json=json.dumps(val),
                attribution="© OpenStreetMap contributors (ODbL)",
                retention_expiry="2999-01-01T00:00:00+00:00")
    apply_tier_columns(lead, val)
    s.add(lead); s.commit(); s.refresh(lead)
    return lead.id


def test_reveal_returns_detail_without_economy_side_effects():
    with Session(lv.engine) as s:
        lid = _seed_lead(s)
        n_purch = len(s.exec(select(PurchasedLead)).all())
        n_tx = len(s.exec(select(CreditTransaction)).all())
    c = TestClient(lv.app)
    token = _login(c, "admin@demo.local", "admin12345")
    r = c.post("/admin/bulk/reveal", json={"lead_ids": [lid]},
               headers={"X-CSRF-Token": token})
    assert r.status_code == 200
    row = r.json()["leads"][0]
    assert row["phone"] == "+441865222222"          # full detail for admin
    with Session(lv.engine) as s:
        assert len(s.exec(select(PurchasedLead)).all()) == n_purch
        assert len(s.exec(select(CreditTransaction)).all()) == n_tx
        assert s.get(Lead, lid).times_sold == 0


def test_export_csv_full_detail_and_attribution():
    with Session(lv.engine) as s:
        lid = _seed_lead(s, "Bulk CSV Lead")
    c = TestClient(lv.app)
    token = _login(c, "admin@demo.local", "admin12345")
    r = c.post("/admin/bulk/export",
               data={"csrf_token": token, "format": "csv",
                     "lead_ids": str(lid)})
    assert r.status_code == 200
    body = r.content.decode("utf-8", errors="replace")
    assert "Bulk CSV Lead" in body and "+441865222222" in body
    assert "OpenStreetMap contributors" in body      # ODbL attribution embedded
    assert "validated" in body                       # tier labels exported


def test_export_xlsx_roundtrip():
    with Session(lv.engine) as s:
        lid = _seed_lead(s, "Bulk XLSX Lead")
    c = TestClient(lv.app)
    token = _login(c, "admin@demo.local", "admin12345")
    r = c.post("/admin/bulk/export",
               data={"csrf_token": token, "format": "xlsx", "lead_ids": str(lid)})
    assert r.status_code == 200
    import io
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(r.content))
    text = " ".join(str(c.value) for row in wb.active.iter_rows() for c in row)
    assert "Bulk XLSX Lead" in text


def test_buyer_cannot_touch_bulk_endpoints_or_see_controls():
    c = TestClient(lv.app)
    token = _login(c, "buyer@demo.local", "buyer12345")
    r = c.post("/admin/bulk/reveal", json={"lead_ids": [1]},
               headers={"X-CSRF-Token": token})
    assert r.status_code in (302, 303, 401, 403)
    html = c.get("/app/find").text
    assert "Unlock selected" not in html
    assert "Export all" not in html


def test_admin_can_view_find_page_with_controls():
    c = TestClient(lv.app)
    _login(c, "admin@demo.local", "admin12345")
    r = c.get("/app/find")
    assert r.status_code == 200
    assert "Unlock selected" in r.text and "Export all" in r.text
```
(Same admin-seeding note as Task 8. Also update `base.html` nav if needed so an admin visiting /app/find doesn't crash the sidebar — read the template's role branches; the admin sidebar already exists, page renders inside it.)

- [ ] **Step 2: Run — FAIL**, then implement per the Interfaces block. Key separation rule: routes_admin_bulk.py imports `unlock_view`, `with_quality`, serve-filter helpers — and NOTHING from app/core/purchasing (the buyer economy module). Serveability check per lead mirrors estimate's filter chain (is_expired, lead_opted_out, passes_serve_filters); suppression is buyer-scoped and does not apply to the owner. `find.html`: guard all admin JS/markup behind `{% if user.role == 'admin' %}`; "Export all" posts the CURRENT composition (state.advancedComposition or compiled composition) as the `composition` field.

- [ ] **Step 3: Run** — `python -m pytest tests/test_admin_bulk_export.py tests/test_find_page.py tests/test_find_routes.py tests/test_purchasing.py tests/ -q` → green (buyer unlock tests UNMODIFIED)
- [ ] **Step 4: Commit**

```bash
git add app/web/routes_admin_bulk.py app/leadvault.py app/web/routes_find.py app/web/templates/find.html app/engine/export.py tests/test_admin_bulk_export.py
git commit -m "feat(admin): bulk unlock/export - economy-bypassing owner path, compliance spine intact, CSV+XLSX"
```

---

### Task 12: Boundary guards + runbook

**Files:**
- Modify: `tests/test_geo_grepclean.py` → extend or create `tests/test_bulk_grepclean.py`
- Modify: `README.md`
- Test: the new grep test itself

- [ ] **Step 1:** New `tests/test_bulk_grepclean.py` mirroring the geo grepclean pattern: `app/core/**/*.py` free of `geofabrik|osmium|pbf` (case-insensitive). Run — must PASS already; if it fails, MOVE the leak, never weaken. Confirm `tests/test_core_import_boundary.py` still passes with NO new allowlist entries (bulk modules must not be imported from core).
- [ ] **Step 2:** README: "Bulk OSM ingestion" runbook section — honest copy: extract sizes (GB ≈ 1.5–2 GB), parse time (tens of minutes), disk (node cache several GB, auto-deleted), no per-lead enrichment during bulk, funnel numbers are measured on the admin page after import, re-import cadence manual/weekly, whole-planet out of scope, ODbL + Geofabrik attribution, Postgres trigger conditions (from spec §3.3).
- [ ] **Step 3:** `python -m pytest tests/test_bulk_grepclean.py tests/test_core_import_boundary.py -v` → PASS. Commit:

```bash
git add tests/test_bulk_grepclean.py README.md
git commit -m "test(bulk): grep-clean core of bulk vendor strings + honest runbook"
```

---

### Task 13: Full-suite pass + polish sweep

- [ ] **Step 1:** `python -m pytest tests/ -q` — green (expected ≈ 395 + ~35 new).
- [ ] **Step 2:** Jargon sweep on buyer pages (find, audiences, purchased): no new engine jargon leaked (bulk work is admin-side; verify the admin-only find controls don't leak strings to buyers — already tested, spot-check rendered HTML). Admin ingest page copy: honest (sizes, times, no-enrichment note, funnel labels).
- [ ] **Step 3:** Grep sweep: no references to `run_bulk_import`/`bulk_jobs` from buyer routes; `var/` is gitignored (add if missing).
- [ ] **Step 4:** Commit any fixes: `chore(bulk): polish sweep`.

---

### Task 14: Browser verification (orchestrator, Playwright MCP) — Monaco live E2E

Start the app; verify in the browser with screenshots (ping the user first — standing preference):

1. **Admin bulk import (LIVE, tiny):** /admin/ingest → Bulk import card shows honest copy + region select → pick **Monaco (~3 MB real download)** → start → progress counts update while running (elements_seen/matched/stored/hot) → status reaches done → funnel numbers displayed. (Network use is deliberate and small; GB is NOT run in verification.)
2. **Coverage honesty end-to-end:** buyer find page → geo step → Monaco now shows a real lead count (was "0 — not yet ingested" before the import — capture before/after screenshots); new categories from Monaco businesses appear in the Who list with counts.
3. **Estimate at new volume:** whole-country Monaco + "Any validated contact" → honest count + tier chips on samples; a quality-bar change (phone-only) visibly narrows the count (SQL gate + Python gate agreeing).
4. **Admin bulk unlock/export:** as admin on /app/find → run a search → select-all → "Unlock selected" reveals full details inline → "Export all (N)" downloads CSV and XLSX; open the CSV, confirm full detail + ODbL attribution line + tier labels. Verify buyer login sees NO bulk controls.
5. **Economy untouched:** buyer unlocks one lead normally (credits decrement; purchased flow works as before).
6. **Cancel path:** start a second Monaco import → cancel mid-run → status "cancelled", no crash, partial counts shown.
7. **Overpass path intact:** run a small ad-hoc Overpass city ingest from the existing form.
8. **Console:** zero JS errors throughout.

Fix anything found (test-first where testable, commit each fix).

---

### Task 15: Whole-branch review → PR

Run the final whole-branch review (most capable model) over `feature/bulk-osm` (base = branch-start SHA recorded in the ledger), fix findings, then open a PR to `feature/ux-overhaul`? NO — base the PR on **master** only if PR #1 has merged by then; otherwise open PR base `feature/ux-overhaul` and note the stacking in the PR body. PR body: scope summary, measured Monaco funnel numbers + benchmark p95 numbers (honest, from Task 10/14 evidence), accepted-debt list from the ledger, fix-confirmation table. STOP for the user's merge review.

## Self-Review (plan-writing time)

- Spec coverage: §1.1-1.2 (T6, T5), §1.3 (T7), §1.4 (T8), §2 (T3, T4), §3.1 (T2), §3.2 (T1, T9, T10), §3.3 decision documented (T12 README), §4 funnel honesty (T7 counts + T8 display + T14.1), §4b admin bulk (T11), §5 boundaries (T12 + constraints), §6 fixture/tests (T5 + throughout), Monaco E2E (T14).
- Type consistency: `stream_business_leads(pbf_path, *, source_key, node_cache_path, progress_cb)` (T5) consumed in T7; `download_extract(region_key, *, dest_dir, http_get, max_age_days)` + `REGIONS`/`GEOFABRIK` (T6) in T7/T8; `run_bulk_import(session, region_key, *, scoring_profile_key, pbf_path, batch_size, cancel_check, on_progress, actor_user_id)` (T7) in T8; `apply_tier_columns(lead, validation)`/`ordinal(tier)`/`FIELDS` (T2) in T7/T10/T11 tests; `profile_clauses(profile)` (T10) in run_estimate; `matching_by_composition(..., extra_clauses=)` (T9) in T10.
- Known judgment calls delegated with guardrails: pyosmium API drift (T5/T6 notes), new-vs-merged detection (T7 note), monkeypatch-able run_fn resolution (T8 note), rows_to_csv guard reuse (T11), admin seeding in tests (T8/T11 notes).
