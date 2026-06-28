# LeadVault Slice One — Plan 1: Inventory & Intelligence Backend

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the source-agnostic data backbone of the LeadVault marketplace: pluggable source adapters (OSM/Overpass first, urlscan-fingerprint second) feeding an ingestion pipeline that normalizes → dedups → enriches → scores (via a pluggable scoring profile) → compliance-checks → stores `Lead` records with full source/license/compliance metadata.

**Architecture:** A vertical-free `app/core/` (DB models, taxonomy, compliance, audit) plus `app/adapters/`, `app/enrich/`, `app/scoring/profiles/`, and `app/ingestion/`. Adapters map any source into one canonical `NormalizedLead`; the ingestion pipeline is the only consumer of adapters; scoring is profile-agnostic with `utility_energy` as one registered profile. No vertical or source name may leak into `app/core/`.

**Tech Stack:** Python 3.11 (`.venv/Scripts/python`), FastAPI/SQLModel/SQLite (Postgres-ready models), `requests` (Overpass), reuse of the existing `app/engine/*` fingerprint engine. pytest.

## Global Constraints

- Interpreter is `.venv/Scripts/python`; tests run with `.venv/Scripts/python -m pytest`.
- **Source-agnostic:** the marketplace **core** (`app/core/*`) must never import an adapter and must contain **no** `energy`, `utility`, `osm`, or `overpass` strings (case-insensitive). Those live only in `app/adapters/osm.py`, `app/scoring/profiles/utility_energy.py`, and seed data. A grep over `app/core/` is an acceptance check (Task 12).
- **Category-agnostic:** categories are DB rows (`LeadCategory`), never Python enums.
- **Scoring is profile-agnostic:** `app/scoring/engine.py` knows nothing about any vertical; profiles live in `app/scoring/profiles/`.
- **Business-level data only** — no personal decision-maker fields are collected or stored in slice one.
- Every `Lead` MUST carry `source_key`, `source_name`, `source_url`, `source_license`, `lawful_basis`, `date_discovered`. Compliance defaults: `opt_out_status="clear"`, `suppression_status="clear"`.
- New DB file is `leadvault.db` (gitignored via the existing `*.db` rule). Do NOT commit it.
- TDD: failing test → minimal code → passing test → commit. Adapters/enrichment/ingestion tests use injected fakes — **no live network in tests**.
- The existing `app/engine/*` modules are reused as internal libraries and must not be modified by this plan.

---

## File Structure

```
app/
  core/
    __init__.py
    db.py            # all slice-one SQLModel entities + init_db + _now
    taxonomy.py      # LeadCategory CRUD + CategoryMapping + generic seed
    compliance.py    # is_suppressed, is_opted_out, audit, host_of
    dedup.py         # dedupe_key, find_existing
  adapters/
    __init__.py
    base.py          # SourceMeta, AdapterQuery, NormalizedLead, LeadSourceAdapter protocol
    registry.py      # register/get adapters
    osm.py           # Overpass adapter (first concrete source)
    urlscan_fingerprint.py  # existing engine wrapped as adapter (second)
  enrich/
    __init__.py
    website.py       # reachability + tech intent enrichment (reuses engine.enrich)
  scoring/
    __init__.py
    engine.py        # generic_subscores + score(lead, profile)
    profiles/
      __init__.py
      base.py        # ScoringProfile protocol
      registry.py    # profile key -> profile
      utility_energy.py  # the energy-usage profile (one of many)
  ingestion/
    __init__.py
    pipeline.py      # ingest(): discover->normalize->dedup->enrich->score->comply->store
  seed.py            # seed_sources + seed_taxonomy + seed_profiles entrypoint
tests/
  test_core_db.py, test_taxonomy.py, test_adapter_base.py, test_osm_adapter.py,
  test_urlscan_adapter.py, test_enrich_website.py, test_scoring.py,
  test_utility_profile.py, test_compliance.py, test_dedup.py, test_ingestion.py
```

---

### Task 1: Dependencies + package scaffold

**Files:**
- Modify: `requirements.txt`
- Create: `app/core/__init__.py`, `app/adapters/__init__.py`, `app/enrich/__init__.py`, `app/scoring/__init__.py`, `app/scoring/profiles/__init__.py`, `app/ingestion/__init__.py`
- Test: `tests/test_core_pkg.py`

**Interfaces:**
- Consumes: nothing.
- Produces: importable `app.core`, `app.adapters`, `app.enrich`, `app.scoring`, `app.scoring.profiles`, `app.ingestion` packages.

- [ ] **Step 1: Add deps to `requirements.txt`** (append these lines; keep existing ones)

```
passlib[bcrypt]==1.7.4
itsdangerous==2.2.0
jinja2==3.1.4
```

- [ ] **Step 2: Create the six empty `__init__.py` files** listed above (all empty).

- [ ] **Step 3: Write `tests/test_core_pkg.py`**

```python
import importlib


def test_core_packages_import():
    for mod in ["app.core", "app.adapters", "app.enrich", "app.scoring",
                "app.scoring.profiles", "app.ingestion"]:
        assert importlib.import_module(mod) is not None
```

- [ ] **Step 4: Install new deps**

Run: `.venv/Scripts/python -m pip install -r requirements.txt`
Expected: passlib, bcrypt, itsdangerous, jinja2 install.

- [ ] **Step 5: Run the test**

Run: `.venv/Scripts/python -m pytest tests/test_core_pkg.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt app/core app/adapters app/enrich app/scoring app/ingestion tests/test_core_pkg.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "chore(leadvault): scaffold core/adapters/enrich/scoring/ingestion packages"
```

---

### Task 2: Core database models

**Files:**
- Create: `app/core/db.py`
- Test: `tests/test_core_db.py`

**Interfaces:**
- Consumes: nothing.
- Produces (all SQLModel `table=True`): `User`, `BuyerAccount`, `LeadSource`, `LeadCategory`, `CategoryMapping`, `Lead`, `LeadRecipe`, `PurchasedLead`, `CreditTransaction`, `SuppressionList`, `SuppressionEntry`, `OptOutRequest`, `AuditLog`, `IngestionJob`; `init_db(url="sqlite:///leadvault.db") -> Engine`; `_now() -> str`.

- [ ] **Step 1: Write `tests/test_core_db.py`**

```python
from sqlmodel import Session, select
from app.core.db import init_db, User, Lead, BuyerAccount


def test_models_create_and_query():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        s.add(BuyerAccount(company_name="Acme", credits=100))
        s.add(User(email="a@b.com", password_hash="x", role="buyer"))
        s.add(Lead(business_name="Joe Diner", source_key="k", source_name="n",
                   source_url="u", source_license="ODbL", city="London"))
        s.commit()
        assert s.exec(select(User)).first().email == "a@b.com"
        lead = s.exec(select(Lead)).first()
        assert lead.opt_out_status == "clear"
        assert lead.suppression_status == "clear"
        assert lead.exclusivity_status == "non_exclusive"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_core_db.py -q`
Expected: FAIL (ModuleNotFoundError: app.core.db).

- [ ] **Step 3: Implement `app/core/db.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, create_engine


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str = ""
    role: str = "buyer"  # buyer | admin
    buyer_account_id: int | None = None
    created_at: str = Field(default_factory=_now)


class BuyerAccount(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    company_name: str = ""
    credits: int = 0
    compliance_ack_at: str | None = None
    created_at: str = Field(default_factory=_now)


class LeadSource(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    name: str = ""
    type: str = ""
    url: str = ""
    license: str = ""
    terms_status: str = "permitted"
    regions_json: str = "[]"
    active: bool = True


class LeadCategory(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    label: str = ""
    parent_id: int | None = None


class CategoryMapping(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    source_key: str = Field(index=True)
    external_value: str = Field(index=True)  # e.g. "amenity=restaurant"
    category_key: str = ""


class Lead(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    business_name: str = ""
    category_keys_json: str = "[]"
    # location
    address_line1: str = ""
    city: str = ""
    region: str = ""
    postal_code: str = ""
    country: str = ""
    latitude: float | None = None
    longitude: float | None = None
    # contact (business-level only)
    phone: str = ""
    public_email: str = ""
    website_url: str = ""
    # flexible attribute + intent blobs
    attributes_json: str = "{}"
    intent_json: str = "{}"
    # scoring
    score_total: int = 0
    subscores_json: str = "{}"
    score_explanation: str = ""
    scoring_profile_key: str = ""
    # source + compliance metadata
    source_key: str = ""
    source_name: str = ""
    source_url: str = ""
    source_license: str = ""
    lawful_basis: str = "legitimate_interest_b2b_public"
    date_discovered: str = Field(default_factory=_now)
    date_last_verified: str | None = None
    opt_out_status: str = "clear"        # clear | opted_out
    suppression_status: str = "clear"
    retention_expiry: str | None = None
    # marketplace
    price_credits: int = 1
    exclusivity_status: str = "non_exclusive"
    times_sold: int = 0
    last_sold_at: str | None = None
    dedupe_key: str = Field(default="", index=True)


class LeadRecipe(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    buyer_account_id: int = 0
    name: str = ""
    filters_json: str = "{}"
    scoring_profile_key: str = ""
    created_at: str = Field(default_factory=_now)


class PurchasedLead(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    buyer_account_id: int = Field(index=True)
    lead_id: int = Field(index=True)
    price_credits: int = 0
    status: str = "New"
    notes_json: str = "[]"
    purchased_at: str = Field(default_factory=_now)


class CreditTransaction(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    buyer_account_id: int = Field(index=True)
    delta: int = 0
    reason: str = ""
    ref: str = ""
    created_at: str = Field(default_factory=_now)


class SuppressionList(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    buyer_account_id: int | None = None  # null => global suppression
    name: str = ""
    created_at: str = Field(default_factory=_now)


class SuppressionEntry(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    list_id: int = Field(index=True)
    kind: str = ""  # domain | phone | email | business_name
    value: str = Field(default="", index=True)


class OptOutRequest(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    kind: str = ""  # domain | phone | email
    value: str = Field(default="", index=True)
    applied: bool = False
    created_at: str = Field(default_factory=_now)


class AuditLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    actor_user_id: int | None = None
    action: str = ""
    entity: str = ""
    entity_id: str = ""
    meta_json: str = "{}"
    created_at: str = Field(default_factory=_now)


class IngestionJob(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    adapter_key: str = ""
    query_json: str = "{}"
    status: str = "pending"
    counts_json: str = "{}"
    created_at: str = Field(default_factory=_now)


def init_db(url: str = "sqlite:///leadvault.db"):
    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_core_db.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/db.py tests/test_core_db.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(core): slice-one SQLModel entities"
```

---

### Task 3: Taxonomy (DB-driven categories)

**Files:**
- Create: `app/core/taxonomy.py`
- Test: `tests/test_taxonomy.py`

**Interfaces:**
- Consumes: `LeadCategory`, `CategoryMapping` from `app.core.db`.
- Produces:
  - `seed_taxonomy(session) -> None` (idempotent; seeds GENERIC business categories — no vertical terms)
  - `upsert_category(session, key, label, parent_key=None) -> LeadCategory`
  - `all_categories(session) -> list[dict]`
  - `category_by_key(session, key) -> LeadCategory | None`
  - `add_mapping(session, source_key, external_value, category_key) -> None`
  - `categories_for_external(session, source_key, external_value) -> list[str]`  (returns category keys)

- [ ] **Step 1: Write `tests/test_taxonomy.py`**

```python
from sqlmodel import Session
from app.core.db import init_db
from app.core.taxonomy import (seed_taxonomy, all_categories, category_by_key,
                               add_mapping, categories_for_external, upsert_category)


def test_seed_is_idempotent_and_generic():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        seed_taxonomy(s)
        seed_taxonomy(s)
        keys = [c["key"] for c in all_categories(s)]
        assert keys.count("restaurant") == 1
        assert "gym" in keys and "cafe" in keys
        # taxonomy must be generic — no vertical assumptions baked in
        joined = " ".join(keys).lower()
        assert "energy" not in joined and "utility" not in joined


def test_mapping_resolves_external_to_category_keys():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        seed_taxonomy(s)
        add_mapping(s, "src", "amenity=restaurant", "restaurant")
        assert categories_for_external(s, "src", "amenity=restaurant") == ["restaurant"]
        assert categories_for_external(s, "src", "amenity=unknown") == []
        assert category_by_key(s, "restaurant").label == "Restaurant"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_taxonomy.py -q`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `app/core/taxonomy.py`**

```python
from __future__ import annotations

from sqlmodel import Session, select

from app.core.db import LeadCategory, CategoryMapping

# generic business taxonomy (label, key) — vertical-AGNOSTIC; admins extend at runtime
SEED_CATEGORIES = [
    ("Restaurant", "restaurant"), ("Takeaway", "takeaway"), ("Cafe", "cafe"),
    ("Bakery", "bakery"), ("Bar", "bar"), ("Pub", "pub"), ("Hotel", "hotel"),
    ("Gym", "gym"), ("Fitness Studio", "fitness_studio"), ("Hair Salon", "hair_salon"),
    ("Barber Shop", "barber_shop"), ("Nail Salon", "nail_salon"), ("Spa", "spa"),
    ("Dental Clinic", "dental_clinic"), ("Medical Clinic", "medical_clinic"),
    ("Car Wash", "car_wash"), ("Auto Repair", "auto_repair"),
    ("Convenience Store", "convenience_store"), ("Supermarket", "supermarket"),
    ("Laundromat", "laundromat"), ("Dry Cleaner", "dry_cleaner"),
    ("Butcher", "butcher"), ("Florist", "florist"), ("Pharmacy", "pharmacy"),
    ("Clothing Store", "clothing_store"), ("Hardware Store", "hardware_store"),
    ("Warehouse", "warehouse"), ("Manufacturer", "manufacturer"),
    ("Construction Company", "construction"), ("Real Estate Agency", "real_estate"),
    ("Accountant", "accountant"), ("Law Firm", "law_firm"),
    ("Marketing Agency", "marketing_agency"), ("Recruitment Agency", "recruitment"),
    ("Nursery", "nursery"), ("Cleaning Company", "cleaning"),
]


def upsert_category(session: Session, key: str, label: str,
                    parent_key: str | None = None) -> LeadCategory:
    existing = session.exec(select(LeadCategory).where(LeadCategory.key == key)).first()
    if existing:
        existing.label = label
        session.add(existing)
        session.commit()
        return existing
    parent_id = None
    if parent_key:
        parent = session.exec(select(LeadCategory).where(LeadCategory.key == parent_key)).first()
        parent_id = parent.id if parent else None
    cat = LeadCategory(key=key, label=label, parent_id=parent_id)
    session.add(cat)
    session.commit()
    session.refresh(cat)
    return cat


def seed_taxonomy(session: Session) -> None:
    for label, key in SEED_CATEGORIES:
        if not session.exec(select(LeadCategory).where(LeadCategory.key == key)).first():
            session.add(LeadCategory(key=key, label=label))
    session.commit()


def all_categories(session: Session) -> list[dict]:
    rows = session.exec(select(LeadCategory)).all()
    return [{"id": c.id, "key": c.key, "label": c.label, "parent_id": c.parent_id}
            for c in rows]


def category_by_key(session: Session, key: str) -> LeadCategory | None:
    return session.exec(select(LeadCategory).where(LeadCategory.key == key)).first()


def add_mapping(session: Session, source_key: str, external_value: str,
                category_key: str) -> None:
    session.add(CategoryMapping(source_key=source_key, external_value=external_value,
                                category_key=category_key))
    session.commit()


def categories_for_external(session: Session, source_key: str,
                            external_value: str) -> list[str]:
    rows = session.exec(
        select(CategoryMapping).where(CategoryMapping.source_key == source_key,
                                      CategoryMapping.external_value == external_value)).all()
    return [r.category_key for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_taxonomy.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/taxonomy.py tests/test_taxonomy.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(core): DB-driven category taxonomy"
```

---

### Task 4: Source adapter interface + registry

**Files:**
- Create: `app/adapters/base.py`, `app/adapters/registry.py`
- Test: `tests/test_adapter_base.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `@dataclass SourceMeta(key, name, type, url, license, terms_status="permitted", regions=["*"])`
  - `@dataclass AdapterQuery(area:dict, categories:list[str], limit:int=100, extra:dict={})`
  - `@dataclass NormalizedLead(business_name, category_keys, address:dict, phone="", public_email="", website_url="", opening_hours="", attributes:dict={}, source_key="", source_url="", source_license="", raw_ref="")`
  - `LeadSourceAdapter` Protocol: attribute `meta:SourceMeta`; methods `discover(query)->Iterable[dict]`, `normalize(raw:dict)->NormalizedLead|None`, `attribution()->str`
  - registry: `register(adapter)`, `get(key)->LeadSourceAdapter`, `all_keys()->list[str]`

- [ ] **Step 1: Write `tests/test_adapter_base.py`**

```python
from app.adapters.base import SourceMeta, AdapterQuery, NormalizedLead, LeadSourceAdapter
from app.adapters import registry


class FakeAdapter:
    meta = SourceMeta(key="fake", name="Fake", type="test", url="http://x",
                      license="TEST")

    def discover(self, query):
        return [{"name": "Joe Diner", "cat": "restaurant"},
                {"name": "No Name", "cat": "cafe"}]

    def normalize(self, raw):
        if not raw.get("name"):
            return None
        return NormalizedLead(business_name=raw["name"], category_keys=[raw["cat"]],
                              address={"city": "London"}, source_key=self.meta.key,
                              source_license=self.meta.license, raw_ref=raw["name"])

    def attribution(self):
        return "Fake attribution"


def test_adapter_protocol_and_registry():
    a = FakeAdapter()
    assert isinstance(a, LeadSourceAdapter)  # structural/Protocol check
    registry.register(a)
    assert "fake" in registry.all_keys()
    got = registry.get("fake")
    raws = list(got.discover(AdapterQuery(area={}, categories=["restaurant"])))
    leads = [got.normalize(r) for r in raws]
    assert leads[0].business_name == "Joe Diner"
    assert leads[0].category_keys == ["restaurant"]
    assert leads[0].source_license == "TEST"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_adapter_base.py -q`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `app/adapters/base.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol, runtime_checkable


@dataclass
class SourceMeta:
    key: str
    name: str
    type: str
    url: str
    license: str
    terms_status: str = "permitted"
    regions: list = field(default_factory=lambda: ["*"])


@dataclass
class AdapterQuery:
    area: dict
    categories: list
    limit: int = 100
    extra: dict = field(default_factory=dict)


@dataclass
class NormalizedLead:
    business_name: str
    category_keys: list
    address: dict
    phone: str = ""
    public_email: str = ""
    website_url: str = ""
    opening_hours: str = ""
    attributes: dict = field(default_factory=dict)
    source_key: str = ""
    source_url: str = ""
    source_license: str = ""
    raw_ref: str = ""


@runtime_checkable
class LeadSourceAdapter(Protocol):
    meta: SourceMeta

    def discover(self, query: AdapterQuery) -> Iterable[dict]: ...
    def normalize(self, raw: dict) -> "NormalizedLead | None": ...
    def attribution(self) -> str: ...
```

- [ ] **Step 4: Implement `app/adapters/registry.py`**

```python
from __future__ import annotations

from app.adapters.base import LeadSourceAdapter

_ADAPTERS: dict[str, LeadSourceAdapter] = {}


def register(adapter: LeadSourceAdapter) -> None:
    _ADAPTERS[adapter.meta.key] = adapter


def get(key: str) -> LeadSourceAdapter:
    if key not in _ADAPTERS:
        raise KeyError(f"no adapter registered for '{key}'")
    return _ADAPTERS[key]


def all_keys() -> list[str]:
    return sorted(_ADAPTERS.keys())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_adapter_base.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/adapters/base.py app/adapters/registry.py tests/test_adapter_base.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(adapters): source adapter interface + registry"
```

---

### Task 5: OSM / Overpass adapter

**Files:**
- Create: `app/adapters/osm.py`
- Test: `tests/test_osm_adapter.py`

**Interfaces:**
- Consumes: `SourceMeta`, `AdapterQuery`, `NormalizedLead` from `app.adapters.base`.
- Produces: `class OsmOverpassAdapter` with `meta` (key `"osm_overpass"`, license `"ODbL (OpenStreetMap contributors)"`), `discover(query, *, session=requests)`, `normalize(raw)`, `attribution()`; module map `CATEGORY_TO_OSM: dict[str, str]` (taxonomy key → OSM tag); `build_overpass_ql(area, categories) -> str`.

- [ ] **Step 1: Write `tests/test_osm_adapter.py`**

```python
from app.adapters.osm import OsmOverpassAdapter, build_overpass_ql
from app.adapters.base import AdapterQuery


SAMPLE_ELEMENT = {
    "type": "node", "id": 123, "lat": 51.5, "lon": -0.1,
    "tags": {"name": "Joe Diner", "amenity": "restaurant",
             "addr:housenumber": "12", "addr:street": "High St",
             "addr:city": "London", "addr:postcode": "SW1A 1AA",
             "phone": "+44 20 1234 5678", "website": "https://joediner.co.uk",
             "opening_hours": "Mo-Su 09:00-23:00"}}


class FakeResp:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p


class FakeSession:
    def __init__(self, payload): self.payload = payload; self.last = None
    def post(self, url, data=None, headers=None, timeout=None):
        self.last = data
        return FakeResp(self.payload)


def test_build_overpass_ql_includes_category_tag_and_area():
    ql = build_overpass_ql({"city": "London"}, ["restaurant"])
    assert "amenity" in ql and "restaurant" in ql
    assert "London" in ql


def test_discover_and_normalize():
    sess = FakeSession({"elements": [SAMPLE_ELEMENT]})
    a = OsmOverpassAdapter()
    raws = list(a.discover(AdapterQuery(area={"city": "London"},
                                        categories=["restaurant"]), session=sess))
    assert len(raws) == 1
    lead = a.normalize(raws[0])
    assert lead.business_name == "Joe Diner"
    assert "restaurant" in lead.category_keys
    assert lead.phone == "+44 20 1234 5678"
    assert lead.website_url == "https://joediner.co.uk"
    assert lead.address["city"] == "London"
    assert lead.address["postal_code"] == "SW1A 1AA"
    assert lead.source_key == "osm_overpass"
    assert "ODbL" in lead.source_license


def test_normalize_skips_unnamed():
    a = OsmOverpassAdapter()
    assert a.normalize({"tags": {"amenity": "restaurant"}}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_osm_adapter.py -q`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `app/adapters/osm.py`**

```python
from __future__ import annotations

from typing import Iterable

import requests

from app.adapters.base import SourceMeta, AdapterQuery, NormalizedLead

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = ("LeadVault/0.1 (+https://example.com/contact; "
              "youssef.zaki@student.giu-uni.de)")

# taxonomy key -> OSM tag (key=value). This map is the ONLY place OSM tagging lives.
CATEGORY_TO_OSM = {
    "restaurant": "amenity=restaurant", "takeaway": "amenity=fast_food",
    "cafe": "amenity=cafe", "bakery": "shop=bakery", "bar": "amenity=bar",
    "pub": "amenity=pub", "hotel": "tourism=hotel", "gym": "leisure=fitness_centre",
    "fitness_studio": "leisure=fitness_centre", "hair_salon": "shop=hairdresser",
    "barber_shop": "shop=hairdresser", "nail_salon": "shop=beauty", "spa": "leisure=spa",
    "dental_clinic": "amenity=dentist", "medical_clinic": "amenity=clinic",
    "car_wash": "amenity=car_wash", "auto_repair": "shop=car_repair",
    "convenience_store": "shop=convenience", "supermarket": "shop=supermarket",
    "laundromat": "shop=laundry", "dry_cleaner": "shop=dry_cleaning",
    "butcher": "shop=butcher", "florist": "shop=florist", "pharmacy": "amenity=pharmacy",
    "clothing_store": "shop=clothes", "hardware_store": "shop=hardware",
}
_OSM_TO_CATEGORY = {v: k for k, v in CATEGORY_TO_OSM.items()}


def build_overpass_ql(area: dict, categories: list[str], limit: int = 100) -> str:
    city = area.get("city") or area.get("region") or ""
    selectors = []
    for c in categories:
        tag = CATEGORY_TO_OSM.get(c)
        if not tag:
            continue
        k, v = tag.split("=", 1)
        selectors.append(f'node["{k}"="{v}"](area.searchArea);')
        selectors.append(f'way["{k}"="{v}"](area.searchArea);')
    body = "\n".join(selectors)
    return (f'[out:json][timeout:60];\n'
            f'area["name"="{city}"]->.searchArea;\n'
            f'(\n{body}\n);\n'
            f'out center {limit};')


class OsmOverpassAdapter:
    meta = SourceMeta(key="osm_overpass", name="OpenStreetMap (Overpass)",
                      type="open_data", url=OVERPASS_URL,
                      license="ODbL (OpenStreetMap contributors)")

    def discover(self, query: AdapterQuery, *, session=requests) -> Iterable[dict]:
        ql = build_overpass_ql(query.area, query.categories, query.limit)
        resp = session.post(OVERPASS_URL, data={"data": ql},
                            headers={"User-Agent": USER_AGENT}, timeout=90)
        resp.raise_for_status()
        return resp.json().get("elements", [])

    def normalize(self, raw: dict) -> NormalizedLead | None:
        tags = raw.get("tags") or {}
        name = tags.get("name")
        if not name:
            return None
        cats = []
        for tag_key in ("amenity", "shop", "leisure", "tourism"):
            if tag_key in tags:
                ext = f"{tag_key}={tags[tag_key]}"
                if ext in _OSM_TO_CATEGORY:
                    cats.append(_OSM_TO_CATEGORY[ext])
        lat = raw.get("lat") or (raw.get("center") or {}).get("lat")
        lon = raw.get("lon") or (raw.get("center") or {}).get("lon")
        street = " ".join(x for x in (tags.get("addr:housenumber"),
                                      tags.get("addr:street")) if x)
        return NormalizedLead(
            business_name=name,
            category_keys=cats,
            address={"line1": street, "city": tags.get("addr:city", ""),
                     "region": tags.get("addr:state", ""),
                     "postal_code": tags.get("addr:postcode", ""),
                     "country": tags.get("addr:country", ""),
                     "lat": lat, "lon": lon},
            phone=tags.get("phone") or tags.get("contact:phone", ""),
            public_email=tags.get("email") or tags.get("contact:email", ""),
            website_url=tags.get("website") or tags.get("contact:website", ""),
            opening_hours=tags.get("opening_hours", ""),
            attributes={"open_7_days": "Su" in tags.get("opening_hours", "")
                        or "Mo-Su" in tags.get("opening_hours", "")},
            source_key=self.meta.key, source_url=OVERPASS_URL,
            source_license=self.meta.license,
            raw_ref=f"{raw.get('type','node')}/{raw.get('id','')}")

    def attribution(self) -> str:
        return "© OpenStreetMap contributors, ODbL (https://www.openstreetmap.org/copyright)"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_osm_adapter.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/adapters/osm.py tests/test_osm_adapter.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(adapters): OSM/Overpass source adapter"
```

---

### Task 6: urlscan-fingerprint adapter (proves a second, different source)

**Files:**
- Create: `app/adapters/urlscan_fingerprint.py`
- Test: `tests/test_urlscan_adapter.py`

**Interfaces:**
- Consumes: `SourceMeta`, `AdapterQuery`, `NormalizedLead`; existing `app.engine.recipes.get_builtin`, `app.engine.enrich.analyse`, `app.engine.enrich.norm_url`.
- Produces: `class UrlscanFingerprintAdapter` with `meta` (key `"urlscan_fingerprint"`, type `"tech_detection"`, license `"urlscan.io ToS (public scan index)"`), `discover(query, *, hosts_fn=None)`, `normalize(raw, *, fetch_fn=fetch)`, `attribution()`. `query.extra["recipe_id"]` selects the fingerprint recipe; `query.extra["hosts"]` may supply hosts directly (manual bypass).

- [ ] **Step 1: Write `tests/test_urlscan_adapter.py`**

```python
from app.adapters.urlscan_fingerprint import UrlscanFingerprintAdapter
from app.adapters.base import AdapterQuery

HTML = ('<html><title>Marios</title><body>'
        '<script src="https://fbgcdn.com/embedder/js/ewm2.js"></script>'
        '<a href="mailto:info@marios.com">e</a></body></html>')


def test_discover_uses_supplied_hosts_and_normalize_detects_tech():
    a = UrlscanFingerprintAdapter()
    q = AdapterQuery(area={}, categories=[],
                     extra={"recipe_id": "gloriafood", "hosts": ["marios.com"]})
    raws = list(a.discover(q))
    assert raws == [{"host": "marios.com", "recipe_id": "gloriafood"}]

    def fake_fetch(url, **kw):
        return url, HTML
    lead = a.normalize(raws[0], fetch_fn=fake_fetch)
    assert lead.business_name == "Marios"
    assert lead.website_url.startswith("https://marios.com")
    assert lead.attributes.get("on_platform") is True
    assert lead.source_key == "urlscan_fingerprint"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_urlscan_adapter.py -q`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `app/adapters/urlscan_fingerprint.py`**

```python
from __future__ import annotations

from typing import Iterable

from app.adapters.base import SourceMeta, AdapterQuery, NormalizedLead
from app.engine.recipes import get_builtin
from app.engine.discover import discover as engine_discover
from app.engine.enrich import analyse, fetch as engine_fetch, norm_url


class UrlscanFingerprintAdapter:
    meta = SourceMeta(key="urlscan_fingerprint", name="urlscan.io fingerprint",
                      type="tech_detection", url="https://urlscan.io",
                      license="urlscan.io ToS (public scan index)")

    def discover(self, query: AdapterQuery, *, hosts_fn=None) -> Iterable[dict]:
        recipe_id = query.extra.get("recipe_id", "")
        hosts = query.extra.get("hosts")
        if hosts is None:
            recipe = get_builtin(recipe_id)
            fn = hosts_fn or (lambda r: engine_discover(
                r, source="urlscan", limit=query.limit))
            hosts = fn(recipe) if recipe else []
        return [{"host": h, "recipe_id": recipe_id} for h in hosts]

    def normalize(self, raw: dict, *, fetch_fn=engine_fetch) -> NormalizedLead | None:
        host = raw.get("host")
        if not host:
            return None
        recipe = get_builtin(raw.get("recipe_id", ""))
        url = norm_url(host)
        final_url, html = fetch_fn(url)
        if not html or recipe is None:
            return None
        lead = analyse(recipe, final_url or url, html)
        return NormalizedLead(
            business_name=lead.name,
            category_keys=[],
            address={"country": lead.country},
            phone=lead.phones[0] if lead.phones else "",
            public_email=lead.emails[0] if lead.emails else "",
            website_url=lead.website,
            attributes={"on_platform": lead.on_platform,
                        "matched_fingerprint": lead.matched,
                        "detected_platform": recipe.type},
            source_key=self.meta.key, source_url=lead.website,
            source_license=self.meta.license, raw_ref=host)

    def attribution(self) -> str:
        return "Technology detected from public page source via urlscan.io index"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_urlscan_adapter.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/adapters/urlscan_fingerprint.py tests/test_urlscan_adapter.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(adapters): urlscan-fingerprint adapter (second source)"
```

---

### Task 7: Website / tech enrichment

**Files:**
- Create: `app/enrich/website.py`
- Test: `tests/test_enrich_website.py`

**Interfaces:**
- Consumes: `NormalizedLead`; existing `app.engine.enrich.fetch`.
- Produces: `enrich_website(lead:NormalizedLead, *, fetch_fn=fetch) -> dict` returning intent/digital signals: `{website_reachable, ssl, online_ordering_detected, booking_detected, payment_provider_detected, ecommerce_detected, last_scanned}`. Module map `INTENT_FINGERPRINTS: dict[str, list[str]]`.

- [ ] **Step 1: Write `tests/test_enrich_website.py`**

```python
from app.adapters.base import NormalizedLead
from app.enrich.website import enrich_website


def test_no_website_is_unreachable():
    lead = NormalizedLead(business_name="X", category_keys=[], address={})
    out = enrich_website(lead, fetch_fn=lambda u, **k: (None, None))
    assert out["website_reachable"] is False


def test_detects_online_ordering_and_ssl():
    lead = NormalizedLead(business_name="X", category_keys=[], address={},
                          website_url="https://x.com/")
    html = '<html><script src="https://fbgcdn.com/embedder/js/ewm2.js"></script></html>'
    out = enrich_website(lead, fetch_fn=lambda u, **k: ("https://x.com/", html))
    assert out["website_reachable"] is True
    assert out["ssl"] is True
    assert out["online_ordering_detected"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_enrich_website.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `app/enrich/website.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from app.adapters.base import NormalizedLead
from app.engine.enrich import fetch

# intent signal -> substrings that indicate it in page source
INTENT_FINGERPRINTS = {
    "online_ordering_detected": ["fbgcdn.com", "ewm2.js", "gloriafood", "chownow",
                                 "flipdish", "toasttab", "slicelife"],
    "booking_detected": ["calendly.com", "acuityscheduling", "simplybook",
                         "setmore", "mindbodyonline"],
    "payment_provider_detected": ["js.stripe.com", "paypal.com/sdk", "squareup",
                                  "klarna", "adyen", "gocardless"],
    "ecommerce_detected": ["cdn.shopify.com", "woocommerce", "bigcommerce",
                           "magento", "ecwid"],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def enrich_website(lead: NormalizedLead, *, fetch_fn=fetch) -> dict:
    out = {"website_reachable": False, "ssl": False, "online_ordering_detected": False,
           "booking_detected": False, "payment_provider_detected": False,
           "ecommerce_detected": False, "last_scanned": _now()}
    if not lead.website_url:
        return out
    final_url, html = fetch_fn(lead.website_url)
    if not html:
        return out
    out["website_reachable"] = True
    out["ssl"] = (final_url or lead.website_url).startswith("https://")
    low = html.lower()
    for signal, tokens in INTENT_FINGERPRINTS.items():
        out[signal] = any(tok in low for tok in tokens)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_enrich_website.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/enrich/website.py tests/test_enrich_website.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(enrich): website reachability + tech intent enrichment"
```

---

### Task 8: Scoring engine (profile-agnostic) + profile interface

**Files:**
- Create: `app/scoring/engine.py`, `app/scoring/profiles/base.py`, `app/scoring/profiles/registry.py`
- Test: `tests/test_scoring.py`

**Interfaces:**
- Consumes: nothing (operates on a plain `lead` dict — the "lead context").
- Produces:
  - `generic_subscores(lead:dict) -> dict` with keys `contactability, freshness, confidence, completeness, compliance` (each 0–100). The `lead` dict keys used: `phone, public_email, website_url, date_last_verified, source_confidence, opt_out_status, suppression_status, attributes(dict), intent(dict)`.
  - `score(lead:dict, profile) -> dict` returning `{"subscores":{...}, "total":int, "explanation":str}`.
  - `ScoringProfile` Protocol (base.py): attr `key:str`; method `combine(lead:dict, base:dict) -> dict` (same return shape as `score`).
  - registry: `register(profile)`, `get(key)->ScoringProfile`, `all_keys()->list[str]`.

- [ ] **Step 1: Write `tests/test_scoring.py`**

```python
from app.scoring.engine import generic_subscores, score
from app.scoring.profiles import registry


class DummyProfile:
    key = "dummy"
    def combine(self, lead, base):
        total = round(sum(base.values()) / len(base))
        return {"subscores": base, "total": total,
                "explanation": f"dummy total {total}"}


def test_generic_subscores_reward_contact_and_freshness():
    full = generic_subscores({"phone": "1", "public_email": "a@b.com",
                              "website_url": "https://x.com",
                              "date_last_verified": "2026-06-28T00:00:00+00:00",
                              "source_confidence": 90, "opt_out_status": "clear",
                              "suppression_status": "clear"})
    empty = generic_subscores({"opt_out_status": "clear", "suppression_status": "clear"})
    assert full["contactability"] > empty["contactability"]
    assert full["compliance"] == 100
    assert 0 <= full["confidence"] <= 100


def test_score_delegates_to_profile():
    registry.register(DummyProfile())
    out = score({"phone": "1", "opt_out_status": "clear",
                 "suppression_status": "clear"}, registry.get("dummy"))
    assert "total" in out and "explanation" in out and "subscores" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_scoring.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `app/scoring/profiles/base.py`**

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ScoringProfile(Protocol):
    key: str

    def combine(self, lead: dict, base: dict) -> dict: ...
```

- [ ] **Step 4: Implement `app/scoring/profiles/registry.py`**

```python
from __future__ import annotations

from app.scoring.profiles.base import ScoringProfile

_PROFILES: dict[str, ScoringProfile] = {}


def register(profile: ScoringProfile) -> None:
    _PROFILES[profile.key] = profile


def get(key: str) -> ScoringProfile:
    if key not in _PROFILES:
        raise KeyError(f"no scoring profile '{key}'")
    return _PROFILES[key]


def all_keys() -> list[str]:
    return sorted(_PROFILES.keys())
```

- [ ] **Step 5: Implement `app/scoring/engine.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone


def _days_since(iso: str | None) -> float:
    if not iso:
        return 9999.0
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return 9999.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0


def generic_subscores(lead: dict) -> dict:
    contact_fields = [lead.get("phone"), lead.get("public_email"), lead.get("website_url")]
    present = sum(1 for f in contact_fields if f)
    contactability = round(present / 3 * 100)

    days = _days_since(lead.get("date_last_verified"))
    if days <= 7:
        freshness = 100
    elif days <= 30:
        freshness = 80
    elif days <= 90:
        freshness = 50
    elif days < 9999:
        freshness = 25
    else:
        freshness = 0

    confidence = round(min(100, int(lead.get("source_confidence", 50))))
    completeness = round(present / 3 * 100)
    clear = (lead.get("opt_out_status", "clear") == "clear"
             and lead.get("suppression_status", "clear") == "clear")
    compliance = 100 if clear else 0
    return {"contactability": contactability, "freshness": freshness,
            "confidence": confidence, "completeness": completeness,
            "compliance": compliance}


def score(lead: dict, profile) -> dict:
    base = generic_subscores(lead)
    return profile.combine(lead, base)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_scoring.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/scoring/engine.py app/scoring/profiles/base.py app/scoring/profiles/registry.py tests/test_scoring.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(scoring): profile-agnostic scoring engine + profile registry"
```

---

### Task 9: utility_energy scoring profile (one vertical, isolated)

**Files:**
- Create: `app/scoring/profiles/utility_energy.py`
- Test: `tests/test_utility_profile.py`

**Interfaces:**
- Consumes: `generic_subscores` shape (the `base` dict) + `lead` dict (`category_keys:list`, `attributes:dict`).
- Produces: `class UtilityEnergyProfile` with `key="utility_energy"` and `combine(lead, base)`; module constant `HIGH_ENERGY_CATEGORIES:set`. This is the ONLY file in the plan that may contain `energy`/`utility` strings.

- [ ] **Step 1: Write `tests/test_utility_profile.py`**

```python
from app.scoring.engine import generic_subscores, score
from app.scoring.profiles.utility_energy import UtilityEnergyProfile


def test_high_energy_category_scores_higher_than_office():
    p = UtilityEnergyProfile()
    diner = {"category_keys": ["restaurant"], "phone": "1", "public_email": "a@b.com",
             "website_url": "https://x.com", "attributes": {"open_7_days": True},
             "date_last_verified": "2026-06-28T00:00:00+00:00",
             "source_confidence": 90, "opt_out_status": "clear",
             "suppression_status": "clear"}
    office = {"category_keys": ["accountant"], "phone": "1",
              "attributes": {}, "opt_out_status": "clear", "suppression_status": "clear"}
    hi = score(diner, p)
    lo = score(office, p)
    assert hi["total"] > lo["total"]
    assert "energy" in hi["explanation"].lower()
    assert "energy_usage_likelihood" in hi["subscores"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_utility_profile.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `app/scoring/profiles/utility_energy.py`**

```python
from __future__ import annotations

# categories that typically have high energy usage (heating, refrigeration, machines)
HIGH_ENERGY_CATEGORIES = {
    "restaurant", "takeaway", "cafe", "bakery", "hotel", "gym", "fitness_studio",
    "car_wash", "laundromat", "dry_cleaner", "convenience_store", "supermarket",
    "butcher", "warehouse", "manufacturer", "spa",
}


class UtilityEnergyProfile:
    key = "utility_energy"

    def _energy_likelihood(self, lead: dict) -> int:
        cats = set(lead.get("category_keys") or [])
        attrs = lead.get("attributes") or {}
        score = 30
        if cats & HIGH_ENERGY_CATEGORIES:
            score = 80
        if attrs.get("open_7_days"):
            score += 10
        if attrs.get("number_of_locations", 1) and attrs.get("number_of_locations", 1) > 1:
            score += 10
        return min(100, score)

    def combine(self, lead: dict, base: dict) -> dict:
        energy = self._energy_likelihood(lead)
        fit = energy  # for this vertical, fit == energy-usage likelihood
        subs = dict(base)
        subs["energy_usage_likelihood"] = energy
        subs["fit"] = fit
        # weighted blend
        total = round(
            0.35 * energy + 0.20 * base["contactability"] + 0.15 * base["freshness"]
            + 0.15 * base["confidence"] + 0.15 * base["compliance"])
        cats = ", ".join(lead.get("category_keys") or []) or "uncategorised"
        bits = [f"category: {cats}"]
        if (lead.get("attributes") or {}).get("open_7_days"):
            bits.append("open 7 days")
        if lead.get("phone"):
            bits.append("public phone")
        bits.append(f"energy-usage likelihood {energy}")
        explanation = f"Scored {total} — " + ", ".join(bits) + "."
        return {"subscores": subs, "total": total, "explanation": explanation}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_utility_profile.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/scoring/profiles/utility_energy.py tests/test_utility_profile.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(scoring): utility_energy profile (isolated vertical)"
```

---

### Task 10: Compliance primitives + audit

**Files:**
- Create: `app/core/compliance.py`
- Test: `tests/test_compliance.py`

**Interfaces:**
- Consumes: `OptOutRequest`, `SuppressionList`, `SuppressionEntry`, `AuditLog` from `app.core.db`.
- Produces:
  - `host_of(url:str) -> str` (bare host, strip `www.`)
  - `is_opted_out(session, *, domain="", phone="", email="") -> bool`
  - `is_suppressed(session, buyer_account_id:int|None, *, domain="", phone="", email="", business_name="") -> bool` (matches global lists where `buyer_account_id is None` AND the buyer's own lists)
  - `audit(session, actor_user_id, action, entity, entity_id, meta:dict|None=None) -> AuditLog`

- [ ] **Step 1: Write `tests/test_compliance.py`**

```python
from sqlmodel import Session
from app.core.db import (init_db, OptOutRequest, SuppressionList, SuppressionEntry,
                         AuditLog)
from app.core.compliance import host_of, is_opted_out, is_suppressed, audit
from sqlmodel import select


def test_host_of():
    assert host_of("https://www.joe.co.uk/menu") == "joe.co.uk"
    assert host_of("joe.com") == "joe.com"


def test_opt_out_and_suppression():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        s.add(OptOutRequest(kind="domain", value="optout.com", applied=True))
        gl = SuppressionList(buyer_account_id=None, name="global")
        s.add(gl); s.commit(); s.refresh(gl)
        s.add(SuppressionEntry(list_id=gl.id, kind="phone", value="+44 123"))
        bl = SuppressionList(buyer_account_id=7, name="buyer7")
        s.add(bl); s.commit(); s.refresh(bl)
        s.add(SuppressionEntry(list_id=bl.id, kind="domain", value="mine.com"))
        s.commit()

        assert is_opted_out(s, domain="optout.com") is True
        assert is_opted_out(s, domain="ok.com") is False
        assert is_suppressed(s, 7, phone="+44 123") is True       # global list
        assert is_suppressed(s, 7, domain="mine.com") is True     # buyer's own
        assert is_suppressed(s, 9, domain="mine.com") is False    # other buyer


def test_audit_writes_row():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        audit(s, 1, "unlock", "Lead", "42", {"price": 3})
        rows = s.exec(select(AuditLog)).all()
        assert rows[0].action == "unlock" and rows[0].entity_id == "42"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_compliance.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `app/core/compliance.py`**

```python
from __future__ import annotations

import json
from urllib.parse import urlsplit

from sqlmodel import Session, select

from app.core.db import (OptOutRequest, SuppressionList, SuppressionEntry, AuditLog)


def host_of(url: str) -> str:
    if not url:
        return ""
    netloc = urlsplit(url if "//" in url else "https://" + url).netloc.lower()
    netloc = netloc.split(":")[0]
    return netloc[4:] if netloc.startswith("www.") else netloc


def is_opted_out(session: Session, *, domain: str = "", phone: str = "",
                 email: str = "") -> bool:
    checks = [("domain", domain), ("phone", phone), ("email", email)]
    for kind, value in checks:
        if not value:
            continue
        hit = session.exec(select(OptOutRequest).where(
            OptOutRequest.kind == kind, OptOutRequest.value == value,
            OptOutRequest.applied == True)).first()  # noqa: E712
        if hit:
            return True
    return False


def is_suppressed(session: Session, buyer_account_id: int | None, *, domain: str = "",
                  phone: str = "", email: str = "", business_name: str = "") -> bool:
    lists = session.exec(select(SuppressionList).where(
        (SuppressionList.buyer_account_id == None)  # noqa: E711  (global)
        | (SuppressionList.buyer_account_id == buyer_account_id))).all()
    list_ids = [l.id for l in lists]
    if not list_ids:
        return False
    checks = [("domain", domain), ("phone", phone), ("email", email),
              ("business_name", business_name)]
    for kind, value in checks:
        if not value:
            continue
        hit = session.exec(select(SuppressionEntry).where(
            SuppressionEntry.list_id.in_(list_ids),
            SuppressionEntry.kind == kind, SuppressionEntry.value == value)).first()
        if hit:
            return True
    return False


def audit(session: Session, actor_user_id, action: str, entity: str, entity_id: str,
          meta: dict | None = None) -> AuditLog:
    row = AuditLog(actor_user_id=actor_user_id, action=action, entity=entity,
                   entity_id=str(entity_id), meta_json=json.dumps(meta or {}))
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_compliance.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/compliance.py tests/test_compliance.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(core): compliance primitives (opt-out, suppression, audit)"
```

---

### Task 11: Deduplication

**Files:**
- Create: `app/core/dedup.py`
- Test: `tests/test_dedup.py`

**Interfaces:**
- Consumes: `NormalizedLead`; `host_of` from `app.core.compliance`; `Lead` from `app.core.db`.
- Produces:
  - `dedupe_key(lead:NormalizedLead) -> str` (priority: website domain → phone digits → name+city slug)
  - `find_existing(session, key:str) -> Lead | None`

- [ ] **Step 1: Write `tests/test_dedup.py`**

```python
from app.adapters.base import NormalizedLead
from app.core.dedup import dedupe_key, find_existing
from app.core.db import init_db, Lead
from sqlmodel import Session


def _lead(**kw):
    base = dict(business_name="X", category_keys=[], address={})
    base.update(kw)
    return NormalizedLead(**base)


def test_dedupe_key_prefers_domain_then_phone_then_name():
    assert dedupe_key(_lead(website_url="https://www.joe.com/x")) == "domain:joe.com"
    assert dedupe_key(_lead(phone="+44 20 1234 5678")) == "phone:442012345678"
    k = dedupe_key(_lead(business_name="Joe's Diner", address={"city": "London"}))
    assert k == "name:joes-diner|london"


def test_find_existing():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        s.add(Lead(business_name="Joe", dedupe_key="domain:joe.com"))
        s.commit()
        assert find_existing(s, "domain:joe.com") is not None
        assert find_existing(s, "domain:nope.com") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_dedup.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `app/core/dedup.py`**

```python
from __future__ import annotations

import re

from sqlmodel import Session, select

from app.adapters.base import NormalizedLead
from app.core.compliance import host_of
from app.core.db import Lead


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def dedupe_key(lead: NormalizedLead) -> str:
    if lead.website_url:
        host = host_of(lead.website_url)
        if host:
            return f"domain:{host}"
    if lead.phone:
        digits = re.sub(r"\D", "", lead.phone)
        if digits:
            return f"phone:{digits}"
    city = (lead.address or {}).get("city", "")
    return f"name:{_slug(lead.business_name)}|{_slug(city)}"


def find_existing(session: Session, key: str) -> Lead | None:
    if not key:
        return None
    return session.exec(select(Lead).where(Lead.dedupe_key == key)).first()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_dedup.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/dedup.py tests/test_dedup.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(core): deduplication keys"
```

---

### Task 12: Ingestion pipeline + seed + grep acceptance

**Files:**
- Create: `app/ingestion/pipeline.py`, `app/seed.py`
- Test: `tests/test_ingestion.py`

**Interfaces:**
- Consumes: adapter protocol (`discover`/`normalize`/`attribution`), `dedupe_key`/`find_existing`, `enrich_website`, `score`, scoring `registry.get`, `is_opted_out`, `audit`, `host_of`, all DB models, taxonomy seed.
- Produces:
  - `ingest(session, adapter, query:AdapterQuery, *, scoring_profile_key:str, enrich_fn=enrich_website, actor_user_id=None) -> dict` returning counts `{discovered, normalized, stored, skipped_duplicate, skipped_compliance}`; ensures a `LeadSource` row exists for the adapter; writes an `IngestionJob` + `AuditLog`.
  - `app/seed.py`: `seed_all(session)` → `seed_taxonomy` + register adapters + register profiles + seed `LeadSource` rows + seed OSM `CategoryMapping`s.

- [ ] **Step 1: Write `tests/test_ingestion.py`**

```python
from sqlmodel import Session, select
from app.core.db import init_db, Lead, LeadSource, OptOutRequest, IngestionJob
from app.core.taxonomy import seed_taxonomy
from app.adapters.base import SourceMeta, AdapterQuery, NormalizedLead
from app.scoring.profiles.utility_energy import UtilityEnergyProfile
from app.scoring.profiles import registry as profile_registry
from app.ingestion.pipeline import ingest


class FakeAdapter:
    meta = SourceMeta(key="fake_src", name="Fake", type="test", url="http://x",
                      license="TESTLIC")

    def discover(self, query):
        return [{"n": "Joe Diner", "site": "https://joediner.com", "cat": "restaurant"},
                {"n": "Optout Cafe", "site": "https://optout.com", "cat": "cafe"},
                {"n": "Joe Diner Dup", "site": "https://joediner.com", "cat": "restaurant"}]

    def normalize(self, raw):
        return NormalizedLead(business_name=raw["n"], category_keys=[raw["cat"]],
                              address={"city": "London"}, website_url=raw["site"],
                              phone="+44 20 0000 0000", source_key=self.meta.key,
                              source_license=self.meta.license, raw_ref=raw["n"])

    def attribution(self):
        return "fake attribution"


def _fake_enrich(lead, **kw):
    return {"website_reachable": True, "ssl": True, "online_ordering_detected": True,
            "booking_detected": False, "payment_provider_detected": False,
            "ecommerce_detected": False, "last_scanned": "2026-06-28T00:00:00+00:00"}


def test_ingest_dedupes_scores_and_respects_optout():
    engine = init_db("sqlite://")
    profile_registry.register(UtilityEnergyProfile())
    with Session(engine) as s:
        seed_taxonomy(s)
        s.add(OptOutRequest(kind="domain", value="optout.com", applied=True))
        s.commit()
        counts = ingest(s, FakeAdapter(), AdapterQuery(area={"city": "London"},
                        categories=["restaurant", "cafe"]),
                        scoring_profile_key="utility_energy", enrich_fn=_fake_enrich)
        assert counts["discovered"] == 3
        assert counts["skipped_duplicate"] == 1     # Joe Diner Dup
        assert counts["skipped_compliance"] == 1    # optout.com
        assert counts["stored"] == 1
        leads = s.exec(select(Lead)).all()
        assert len(leads) == 1
        lead = leads[0]
        assert lead.business_name == "Joe Diner"
        assert lead.score_total > 0
        assert lead.source_key == "fake_src"
        assert lead.source_license == "TESTLIC"
        assert lead.scoring_profile_key == "utility_energy"
        # source row + ingestion job recorded
        assert s.exec(select(LeadSource).where(LeadSource.key == "fake_src")).first()
        assert s.exec(select(IngestionJob)).first().status == "done"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_ingestion.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `app/ingestion/pipeline.py`**

```python
from __future__ import annotations

import json

from sqlmodel import Session, select

from app.adapters.base import AdapterQuery, NormalizedLead
from app.core.compliance import host_of, is_opted_out, audit
from app.core.db import Lead, LeadSource, IngestionJob, _now
from app.core.dedup import dedupe_key, find_existing
from app.enrich.website import enrich_website
from app.scoring.engine import score
from app.scoring.profiles import registry as profile_registry


def _ensure_source(session: Session, adapter) -> None:
    m = adapter.meta
    if not session.exec(select(LeadSource).where(LeadSource.key == m.key)).first():
        session.add(LeadSource(key=m.key, name=m.name, type=m.type, url=m.url,
                               license=m.license, terms_status=m.terms_status,
                               regions_json=json.dumps(m.regions)))
        session.commit()


def _lead_context(n: NormalizedLead, enrichment: dict) -> dict:
    return {"category_keys": n.category_keys, "phone": n.phone,
            "public_email": n.public_email, "website_url": n.website_url,
            "attributes": {**n.attributes, **enrichment},
            "intent": enrichment, "date_last_verified": _now(),
            "source_confidence": 70, "opt_out_status": "clear",
            "suppression_status": "clear"}


def ingest(session: Session, adapter, query: AdapterQuery, *, scoring_profile_key: str,
           enrich_fn=enrich_website, actor_user_id=None) -> dict:
    _ensure_source(session, adapter)
    profile = profile_registry.get(scoring_profile_key)
    counts = {"discovered": 0, "normalized": 0, "stored": 0,
              "skipped_duplicate": 0, "skipped_compliance": 0}

    for raw in adapter.discover(query):
        counts["discovered"] += 1
        n = adapter.normalize(raw)
        if n is None:
            continue
        counts["normalized"] += 1
        key = dedupe_key(n)
        if find_existing(session, key):
            counts["skipped_duplicate"] += 1
            continue
        domain = host_of(n.website_url)
        if is_opted_out(session, domain=domain, phone=n.phone, email=n.public_email):
            counts["skipped_compliance"] += 1
            continue
        enrichment = enrich_fn(n)
        ctx = _lead_context(n, enrichment)
        scored = score(ctx, profile)
        addr = n.address or {}
        session.add(Lead(
            business_name=n.business_name,
            category_keys_json=json.dumps(n.category_keys),
            address_line1=addr.get("line1", ""), city=addr.get("city", ""),
            region=addr.get("region", ""), postal_code=addr.get("postal_code", ""),
            country=addr.get("country", ""), latitude=addr.get("lat"),
            longitude=addr.get("lon"), phone=n.phone, public_email=n.public_email,
            website_url=n.website_url,
            attributes_json=json.dumps({**n.attributes, **enrichment}),
            intent_json=json.dumps(enrichment),
            score_total=scored["total"], subscores_json=json.dumps(scored["subscores"]),
            score_explanation=scored["explanation"],
            scoring_profile_key=scoring_profile_key,
            source_key=n.source_key, source_name=adapter.meta.name,
            source_url=n.source_url or adapter.meta.url,
            source_license=n.source_license or adapter.meta.license,
            date_last_verified=_now(), dedupe_key=key))
        counts["stored"] += 1

    job = IngestionJob(adapter_key=adapter.meta.key,
                       query_json=json.dumps({"area": query.area,
                                              "categories": query.categories}),
                       status="done", counts_json=json.dumps(counts))
    session.add(job)
    session.commit()
    audit(session, actor_user_id, "ingest", "IngestionJob", str(job.id), counts)
    return counts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_ingestion.py -q`
Expected: PASS.

- [ ] **Step 5: Implement `app/seed.py`**

```python
from __future__ import annotations

import json

from sqlmodel import Session, select

from app.core.db import LeadSource
from app.core.taxonomy import seed_taxonomy, add_mapping, categories_for_external
from app.adapters import registry as adapter_registry
from app.adapters.osm import OsmOverpassAdapter, CATEGORY_TO_OSM
from app.adapters.urlscan_fingerprint import UrlscanFingerprintAdapter
from app.scoring.profiles import registry as profile_registry
from app.scoring.profiles.utility_energy import UtilityEnergyProfile


def _ensure_source(session: Session, meta) -> None:
    if not session.exec(select(LeadSource).where(LeadSource.key == meta.key)).first():
        session.add(LeadSource(key=meta.key, name=meta.name, type=meta.type,
                               url=meta.url, license=meta.license,
                               terms_status=meta.terms_status,
                               regions_json=json.dumps(meta.regions)))
        session.commit()


def register_runtime() -> None:
    """Register adapters + scoring profiles (idempotent, in-memory)."""
    adapter_registry.register(OsmOverpassAdapter())
    adapter_registry.register(UrlscanFingerprintAdapter())
    profile_registry.register(UtilityEnergyProfile())


def seed_all(session: Session) -> None:
    register_runtime()
    seed_taxonomy(session)
    for meta in (OsmOverpassAdapter().meta, UrlscanFingerprintAdapter().meta):
        _ensure_source(session, meta)
    # seed OSM category mappings so the OSM adapter's tags resolve to taxonomy keys
    for cat_key, osm_tag in CATEGORY_TO_OSM.items():
        if not categories_for_external(session, "osm_overpass", osm_tag):
            add_mapping(session, "osm_overpass", osm_tag, cat_key)
```

- [ ] **Step 6: GREP ACCEPTANCE — core must be vertical/source-free**

Run:
```bash
grep -rinE "energy|utility|osm|overpass" app/core/ && echo "LEAK" || echo "CORE CLEAN"
```
Expected: `CORE CLEAN` (no matches). If any line prints, move that logic into an adapter or scoring profile until the grep is clean.

- [ ] **Step 7: Run the full Plan-1 suite**

Run: `.venv/Scripts/python -m pytest tests/test_core_db.py tests/test_taxonomy.py tests/test_adapter_base.py tests/test_osm_adapter.py tests/test_urlscan_adapter.py tests/test_enrich_website.py tests/test_scoring.py tests/test_utility_profile.py tests/test_compliance.py tests/test_dedup.py tests/test_ingestion.py -q`
Expected: all PASS. Also run the whole suite `.venv/Scripts/python -m pytest -q` and confirm the pre-existing engine tests still pass.

- [ ] **Step 8: Commit**

```bash
git add app/ingestion/pipeline.py app/seed.py tests/test_ingestion.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(ingestion): pipeline (dedup+enrich+score+comply+store) + seed + grep-clean core"
```

---

## Self-Review

**Spec coverage (against the slice-one design):**
- Source adapter interface (discover/normalize/attribution) + NormalizedLead → Task 4 ✓
- OSM/Overpass first adapter → Task 5 ✓; urlscan fingerprint second adapter → Task 6 ✓
- Source-agnostic core (grep clean) → Task 12 Step 6 ✓
- Category taxonomy as DB data, not enums → Task 3 ✓
- Scoring profile-agnostic + pluggable; utility_energy = one profile → Tasks 8, 9 ✓
- Enrichment (website/tech intent) → Task 7 ✓
- Ingestion pipeline (discover→normalize→dedup→enrich→score→comply→store) → Task 12 ✓
- Dedup by domain/phone/name+geo → Task 11 ✓
- Compliance metadata on every Lead + opt-out/suppression checks + audit log → Tasks 2, 10, 12 ✓
- Business-level data only (no personal decision-maker fields in models) → Task 2 ✓
- Data model entities (slice-one subset) → Task 2 ✓ (buyer/purchase entities defined here too, exercised in Plan 2)

**Deferred to Plan 2 (Marketplace & Buyer App):** auth/sessions, recipe→query compilation, masked preview vs unlock serializers, credit purchasing + re-buy guard, buyer suppression UI, CSV export of purchased leads, the Jinja dashboard (buyer + admin pages incl. the admin "run ingestion" button that calls Task 12's `ingest`), buyer compliance acknowledgement gate.

**Placeholder scan:** none — every step has runnable code and exact commands.

**Type consistency:** `NormalizedLead` fields used identically across Tasks 4–6, 11, 12. `score(lead, profile)`/`combine(lead, base)` shapes match Tasks 8–9–12. `ingest(...)` counts keys match the Task 12 test. `is_opted_out`/`is_suppressed`/`audit` signatures match Tasks 10 and 12. Scoring + adapter registries share the `register/get/all_keys` shape.

**Known follow-ups (not blockers):** the urlscan adapter's live `discover` path (non-manual) calls the existing engine network discovery — exercised only via the manual `hosts` path in tests (no live network in CI), consistent with the Global Constraints.
