# Unified Find-Leads UX Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Marketplace/Composer/Campaigns tab tangle with one guided find-leads journey (campaign builder → honest two-layer geography → data-driven business types → quality bar → sentence + estimate → results), with per-lead quality tiers visible and every honesty invariant intact.

**Architecture:** New `app/geo` package holds a static GeoNames-derived reference (`GeoRef` table, committed fixture, import script) joined live against inventory counts. New `/app/find` page-set replaces the three tabs (old routes redirect; JSON endpoints aliased). A single server-side assembler turns plain-language answers into a composition; a deterministic sentence renderer describes the *compiled* composition so words can never drift from what runs. Three generic quality profiles compose with campaign profiles by honest intersection (max tier per field).

**Tech Stack:** FastAPI + SQLModel + Jinja2 + Tailwind (CDN, tokens in base.html), vanilla JS, pytest + TestClient. Browser verification via Playwright MCP (done by the orchestrator after the build, Task 14).

**Spec:** `docs/superpowers/specs/2026-07-03-ux-overhaul-design.md`

**Spec deltas (flag to user at final review):**
1. Templates prefill the builder's answers (via a generic template walk), and the final composition is ALWAYS produced by the one generic assembler — rather than delegating final compilation to `compile_campaign`. One code path = the no-drift guarantee the user asked for. `compile_campaign` and `/app/composer/apply-campaign` remain unchanged for compatibility.
2. Ingest requests: buyers CAN file a request for a 0-lead area (row in `IngestRequest`); ingestion itself stays admin-only (admin sees the queue on the admin Ingestion page). This is more useful than admin-only requesting and keeps ingestion admin-gated.

## Global Constraints

- INV-Q1: quality gate is system-enforced; held-back leads never appear in search/estimate/unlock.
- INV-Q2: `verified_live` never self-generated; UI renders it ONLY as a locked "requires licensed provider" state.
- INV-Q6: no SMTP probing (unchanged code, do not touch validators).
- INV-6/INV-8: gated signal paths never enter a composition; no per-campaign strings in generic modules.
- INV-11: business-entity data only. INV-12/13/14/15 (fingerprints) unchanged.
- Grep-clean: `app/core/**/*.py` stays free of quality/provider/vendor strings; NEW: also free of `geonames` (Task 12). The new geo package lives at `app/geo`, NOT `app/core`.
- No network in any seed path: `seed_geo_fixture` reads only the committed CSV. Network happens ONLY in `scripts/import_geonames.py`, run manually.
- No faked coverage: 0-lead areas render honest zero states; greyed recipes are not selectable; "Validated" is never rendered as "Verified".
- Buyer-facing copy: plain language only — no predicate keys, no "min score", no "composition".
- Attribution: GeoNames data is CC BY 4.0 — attribute in the find page footer and README.
- All commands from repo root `C:\Users\BETER\Downloads\leadvein`. Run tests with `python -m pytest <path> -v` (venv `.venv` already active in dev shells; if not: `.venv\Scripts\python -m pytest`).
- Commit after every task (message format `feat(find): ...`, `feat(geo): ...` etc. + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`).
- Design system: reuse `components.html` macros (`ui.card`, `ui.btn`, `ui.badge`, `ui.field`, `ui.empty_state`, `ui.banner`, `ui.lead_card`) and base.html tokens. New macros go in `components.html`.

---

### Task 1: GeoRef reference table + committed fixture + import script

**Files:**
- Create: `app/geo/__init__.py` (empty)
- Create: `app/geo/ref.py`
- Create: `app/geo/data/geo_fixture.csv`
- Create: `scripts/import_geonames.py`
- Modify: `app/leadvault.py` (register model import + seed fixture)
- Test: `tests/test_georef.py`

**Interfaces:**
- Produces: `GeoRef` SQLModel table (`kind` in `country|region|city`; fields `geoname_id:int, country_code:str, country_name:str, admin1_name:str, admin2_name:str, name:str, ascii_name:str, kind:str, population:int`).
- Produces: `app.geo.ref.seed_geo_fixture(session) -> int` (idempotent, CSV-only, no network), `list_countries(session) -> list[GeoRef]`, `search_areas(session, country: str, q: str, limit: int = 60) -> list[GeoRef]` (regions+cities, ranked by population desc, case-insensitive substring on name/ascii_name; empty q returns top-population rows).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_georef.py
"""GeoRef static reference: fixture-only seeding (no network), search, countries."""
from __future__ import annotations

from sqlmodel import Session, select

import app.leadvault as lv
from app.geo.ref import GeoRef, seed_geo_fixture, list_countries, search_areas


def test_seed_geo_fixture_idempotent_and_offline():
    with Session(lv.engine) as s:
        n1 = seed_geo_fixture(s)
        n2 = seed_geo_fixture(s)          # second run inserts nothing
        assert n2 == 0
        total = len(s.exec(select(GeoRef)).all())
        assert total >= 40                # fixture has countries + GB regions + cities
        assert n1 in (0, total)           # 0 if app startup already seeded


def test_countries_include_zero_coverage_ones():
    with Session(lv.engine) as s:
        seed_geo_fixture(s)
        codes = {c.country_code for c in list_countries(s)}
        # Complete country layer: places with no inventory are still findable
        assert {"GB", "US", "DE", "FR"} <= codes
        names = {c.country_name for c in list_countries(s)}
        assert "United Kingdom" in names


def test_search_areas_finds_oxford_ranked():
    with Session(lv.engine) as s:
        seed_geo_fixture(s)
        rows = search_areas(s, "GB", "oxf")
        names = [r.name for r in rows]
        assert "Oxford" in names
        ox = next(r for r in rows if r.name == "Oxford")
        assert ox.kind == "city"
        assert ox.admin1_name == "England"
        assert ox.admin2_name == "Oxfordshire"
        # region rows are searchable too
        regs = search_areas(s, "GB", "oxfordshire")
        assert any(r.kind == "region" and r.name == "Oxfordshire" for r in regs)


def test_search_areas_empty_query_returns_top_population():
    with Session(lv.engine) as s:
        seed_geo_fixture(s)
        rows = search_areas(s, "GB", "")
        assert rows, "empty query lists top areas"
        cities = [r for r in rows if r.kind == "city"]
        assert cities == sorted(cities, key=lambda r: -r.population)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_georef.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.geo'`

- [ ] **Step 3: Implement `app/geo/ref.py`**

```python
"""Static geographic reference (GeoNames-derived snapshot; CC BY 4.0 attribution
in README + find page). Seeding is CSV-only — NO network in any seed path.
Full snapshot import: scripts/import_geonames.py (manual, network)."""
from __future__ import annotations

import csv
import os

from sqlalchemy import func, or_
from sqlmodel import Field, SQLModel, Session, select

_FIXTURE = os.path.join(os.path.dirname(__file__), "data", "geo_fixture.csv")


class GeoRef(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    geoname_id: int = Field(default=0, index=True)
    country_code: str = Field(default="", index=True)   # ISO-2
    country_name: str = ""
    admin1_name: str = Field(default="", index=True)
    admin2_name: str = Field(default="", index=True)
    name: str = Field(default="", index=True)
    ascii_name: str = Field(default="", index=True)
    kind: str = Field(default="city", index=True)       # country | region | city
    population: int = 0


def seed_geo_fixture(session: Session) -> int:
    """Load the committed fixture if the table is empty. Idempotent, offline."""
    if session.exec(select(GeoRef.id).limit(1)).first() is not None:
        return 0
    n = 0
    with open(_FIXTURE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            session.add(GeoRef(
                geoname_id=int(row["geoname_id"] or 0),
                country_code=row["country_code"].upper(),
                country_name=row["country_name"],
                admin1_name=row["admin1_name"],
                admin2_name=row["admin2_name"],
                name=row["name"],
                ascii_name=row["ascii_name"] or row["name"],
                kind=row["kind"],
                population=int(row["population"] or 0),
            ))
            n += 1
    session.commit()
    return n


def list_countries(session: Session) -> list[GeoRef]:
    return list(session.exec(
        select(GeoRef).where(GeoRef.kind == "country")
        .order_by(GeoRef.country_name)).all())


def search_areas(session: Session, country: str, q: str, limit: int = 60) -> list[GeoRef]:
    stmt = select(GeoRef).where(
        GeoRef.country_code == (country or "").upper(),
        GeoRef.kind.in_(("region", "city")))
    q = (q or "").strip().lower()
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(func.lower(GeoRef.ascii_name).like(like),
                              func.lower(GeoRef.name).like(like)))
    stmt = stmt.order_by(GeoRef.population.desc(), GeoRef.name).limit(limit)
    return list(session.exec(stmt).all())
```

- [ ] **Step 4: Write the fixture CSV**

Create `app/geo/data/geo_fixture.csv`. Try the generator first (network allowed here — it is a manual script, not a seed path):

Run: `python scripts/import_geonames.py --write-fixture app/geo/data/geo_fixture.csv` (script written in Step 5 — do Step 5 first if you prefer; either order is fine as long as the fixture ends up committed).

If network is unavailable, hand-write the fallback fixture with EXACTLY these rows (header + minimum viable set; tests assert only on these):

```csv
kind,geoname_id,country_code,country_name,admin1_name,admin2_name,name,ascii_name,population
country,2635167,GB,United Kingdom,,,United Kingdom,United Kingdom,67215293
country,6252001,US,United States,,,United States,United States,331002651
country,2921044,DE,Germany,,,Germany,Germany,83240525
country,3017382,FR,France,,,France,France,67391582
country,2510769,ES,Spain,,,Spain,Spain,47351567
country,3175395,IT,Italy,,,Italy,Italy,59554023
country,2750405,NL,Netherlands,,,Netherlands,Netherlands,17441139
country,2077456,AU,Australia,,,Australia,Australia,25687041
country,6251999,CA,Canada,,,Canada,Canada,38005238
country,2963597,IE,Ireland,,,Ireland,Ireland,4994724
region,6269131,GB,United Kingdom,England,,England,England,55980000
region,2638360,GB,United Kingdom,Scotland,,Scotland,Scotland,5463300
region,2634895,GB,United Kingdom,Wales,,Wales,Wales,3169586
region,2641364,GB,United Kingdom,Northern Ireland,,Northern Ireland,Northern Ireland,1893667
region,2640726,GB,United Kingdom,England,Oxfordshire,Oxfordshire,Oxfordshire,691667
region,2653940,GB,United Kingdom,England,Cambridgeshire,Cambridgeshire,Cambridgeshire,678600
region,2633896,GB,United Kingdom,England,West Yorkshire,West Yorkshire,West Yorkshire,2320214
region,2634185,GB,United Kingdom,England,Norfolk,Norfolk,Norfolk,903680
region,2648109,GB,United Kingdom,England,Greater London,Greater London,Greater London,8961989
city,2640729,GB,United Kingdom,England,Oxfordshire,Oxford,Oxford,171380
city,2656173,GB,United Kingdom,England,Oxfordshire,Banbury,Banbury,47862
city,2655734,GB,United Kingdom,England,Oxfordshire,Bicester,Bicester,32642
city,2653941,GB,United Kingdom,England,Cambridgeshire,Cambridge,Cambridge,128515
city,2640354,GB,United Kingdom,England,Cambridgeshire,Peterborough,Peterborough,163379
city,2644688,GB,United Kingdom,England,West Yorkshire,Leeds,Leeds,455123
city,2643743,GB,United Kingdom,England,Greater London,London,London,8961989
city,2654675,GB,United Kingdom,England,Norfolk,Norwich,Norwich,213166
city,2655603,GB,United Kingdom,England,West Midlands,Birmingham,Birmingham,984333
city,2643123,GB,United Kingdom,England,Greater Manchester,Manchester,Manchester,395515
city,2648579,GB,United Kingdom,Scotland,,Glasgow,Glasgow,626410
city,2650225,GB,United Kingdom,Scotland,,Edinburgh,Edinburgh,464990
city,2653822,GB,United Kingdom,Wales,,Cardiff,Cardiff,447287
city,5128581,US,United States,New York,,New York,New York,8175133
city,5391959,US,United States,California,,San Francisco,San Francisco,864816
city,4930956,US,United States,Massachusetts,,Boston,Boston,667137
city,2950159,DE,Germany,Berlin,,Berlin,Berlin,3426354
city,2911298,DE,Germany,Hamburg,,Hamburg,Hamburg,1739117
city,2988507,FR,France,Île-de-France,,Paris,Paris,2138551
city,2964574,IE,Ireland,Leinster,,Dublin,Dublin,1024027
```

- [ ] **Step 5: Write `scripts/import_geonames.py`**

```python
"""Import a GeoNames snapshot into the geo_ref table (or regenerate the committed fixture).

GeoNames data: https://download.geonames.org/export/dump/ — CC BY 4.0.
This script is the ONLY place geo reference data crosses the network. Seeds never do.

Usage:
  python scripts/import_geonames.py                 # full import into leadvault.db
  python scripts/import_geonames.py --db sqlite:///leadvault.db
  python scripts/import_geonames.py --write-fixture app/geo/data/geo_fixture.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = "https://download.geonames.org/export/dump/"
FIXTURE_COUNTRIES = None  # None = all
FIXTURE_CITY_COUNTRIES = {"GB", "US", "DE", "FR", "IE"}   # fixture keeps cities small


def _fetch(name: str) -> str:
    with urllib.request.urlopen(BASE + name, timeout=120) as r:
        data = r.read()
    if name.endswith(".zip"):
        zf = zipfile.ZipFile(io.BytesIO(data))
        inner = name.replace(".zip", ".txt")
        return zf.read(inner).decode("utf-8")
    return data.decode("utf-8")


def _rows():
    """Yield dict rows (same schema as the fixture CSV) for the full snapshot."""
    countries = {}
    for line in _fetch("countryInfo.txt").splitlines():
        if not line or line.startswith("#"):
            continue
        p = line.split("\t")
        countries[p[0]] = {"name": p[4], "population": int(p[7] or 0),
                           "geoname_id": int(p[16] or 0)}
    for code, c in sorted(countries.items()):
        yield {"kind": "country", "geoname_id": c["geoname_id"], "country_code": code,
               "country_name": c["name"], "admin1_name": "", "admin2_name": "",
               "name": c["name"], "ascii_name": c["name"], "population": c["population"]}

    admin1 = {}   # "GB.ENG" -> "England"
    for line in _fetch("admin1CodesASCII.txt").splitlines():
        p = line.split("\t")
        if len(p) >= 2:
            admin1[p[0]] = p[1]
    admin2 = {}   # "GB.ENG.K2" -> "Oxfordshire"
    for line in _fetch("admin2Codes.txt").splitlines():
        p = line.split("\t")
        if len(p) >= 2:
            admin2[p[0]] = p[1]

    for key, name in sorted(admin1.items()):
        cc = key.split(".")[0]
        if cc not in countries:
            continue
        yield {"kind": "region", "geoname_id": 0, "country_code": cc,
               "country_name": countries[cc]["name"], "admin1_name": name,
               "admin2_name": "", "name": name, "ascii_name": name, "population": 0}
    for key, name in sorted(admin2.items()):
        cc = key.split(".")[0]
        if cc not in countries:
            continue
        a1 = admin1.get(".".join(key.split(".")[:2]), "")
        yield {"kind": "region", "geoname_id": 0, "country_code": cc,
               "country_name": countries[cc]["name"], "admin1_name": a1,
               "admin2_name": name, "name": name, "ascii_name": name, "population": 0}

    for line in _fetch("cities1000.zip").splitlines():
        p = line.split("\t")
        if len(p) < 15:
            continue
        cc = p[8]
        if cc not in countries:
            continue
        a1 = admin1.get(f"{cc}.{p[10]}", "")
        a2 = admin2.get(f"{cc}.{p[10]}.{p[11]}", "")
        yield {"kind": "city", "geoname_id": int(p[0]), "country_code": cc,
               "country_name": countries[cc]["name"], "admin1_name": a1,
               "admin2_name": a2, "name": p[1], "ascii_name": p[2],
               "population": int(p[14] or 0)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.getenv("LEADVAULT_DB", "sqlite:///leadvault.db"))
    ap.add_argument("--write-fixture", default="")
    args = ap.parse_args()

    if args.write_fixture:
        fields = ["kind", "geoname_id", "country_code", "country_name",
                  "admin1_name", "admin2_name", "name", "ascii_name", "population"]
        keep_cities = {"Oxford", "Banbury", "Bicester", "Cambridge", "Peterborough",
                       "Leeds", "London", "Norwich", "Birmingham", "Manchester",
                       "Glasgow", "Edinburgh", "Cardiff", "New York", "San Francisco",
                       "Boston", "Berlin", "Hamburg", "Paris", "Dublin"}
        with open(args.write_fixture, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in _rows():
                if r["kind"] == "country":
                    w.writerow(r)
                elif r["kind"] == "region" and r["country_code"] == "GB":
                    w.writerow(r)
                elif (r["kind"] == "city" and r["country_code"] in FIXTURE_CITY_COUNTRIES
                      and r["name"] in keep_cities):
                    w.writerow(r)
        print(f"fixture written: {args.write_fixture}")
        return

    from sqlmodel import Session, create_engine, select
    from app.geo.ref import GeoRef
    engine = create_engine(args.db)
    GeoRef.metadata.create_all(engine, tables=[GeoRef.__table__])
    with Session(engine) as s:
        # Full import replaces reference rows (safe: pure reference data)
        for row in s.exec(select(GeoRef)).all():
            s.delete(row)
        s.commit()
        n = 0
        for r in _rows():
            s.add(GeoRef(**{k: r[k] for k in r}))
            n += 1
            if n % 5000 == 0:
                s.commit()
        s.commit()
    print(f"imported {n} geo_ref rows")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Wire model registration + fixture seeding into `app/leadvault.py`**

Add next to the existing model-registration imports (after line 12 `import app.fingerprints.models`):

```python
import app.geo.ref  # noqa — register GeoRef table BEFORE init_db
```

Inside `_seed_accounts()`, after `seed_recipes(s)` add:

```python
        from app.geo.ref import seed_geo_fixture
        seed_geo_fixture(s)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_georef.py -v`
Expected: 4 PASS

Run: `python -m pytest tests/ -x -q`
Expected: full suite green (no regressions)

- [ ] **Step 8: Commit**

```bash
git add app/geo scripts/import_geonames.py app/leadvault.py tests/test_georef.py
git commit -m "feat(geo): GeoRef static reference table, committed fixture (offline seed), GeoNames import script"
```

---

### Task 2: Live geo coverage counts

**Files:**
- Create: `app/geo/coverage.py`
- Test: `tests/test_geo_coverage.py`

**Interfaces:**
- Consumes: `Lead` model; `app.core.retention.is_expired`, `app.core.compliance.lead_opted_out`, `app.core.serve_filters.passes_serve_filters`.
- Produces: `geo_lead_counts(session) -> dict` with keys `countries: dict[str,int]` (ISO2→count), `cities: dict[tuple[str,str],int]` ((ISO2, city_lower)→count), `regions: dict[tuple[str,str],int]`, `city_names: dict[str,str]` (city_lower→original casing, for "other areas"); TTL-cached 60s; `invalidate_geo_counts() -> None`.

Counts are HONEST: only leads that would actually be servable (not expired, not opted out, pass serve filters incl. the quality gate). Buyer-specific suppression is per-buyer, so it is not part of global counts.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_geo_coverage.py
"""Coverage counts are honest: only serveable leads count; gate-held leads don't."""
from __future__ import annotations

import json

from sqlmodel import Session

import app.leadvault as lv
from app.core.db import Lead
from app.geo.coverage import geo_lead_counts, invalidate_geo_counts


def _lead(city, country, validated=True, **kw):
    v = {"profile": {"tier": "validated"},
         "phone": {"tier": "validated" if validated else "present"},
         "email": {"tier": "absent"}}
    return Lead(business_name=f"biz-{city}", city=city, country=country,
                phone="+441865000000", category_keys_json='["bakery"]',
                validation_json=json.dumps(v), **kw)


def test_counts_only_serveable_leads():
    with Session(lv.engine) as s:
        s.add(_lead("Coverageville", "GB", validated=True))
        s.add(_lead("Coverageville", "GB", validated=True))
        s.add(_lead("Coverageville", "GB", validated=False))  # gate-held: not counted
        s.commit()
    invalidate_geo_counts()
    with Session(lv.engine) as s:
        counts = geo_lead_counts(s)
    assert counts["cities"][("GB", "coverageville")] == 2
    assert counts["countries"]["GB"] >= 2
    assert counts["city_names"]["coverageville"] == "Coverageville"


def test_cache_invalidation():
    with Session(lv.engine) as s:
        before = geo_lead_counts(s)["cities"].get(("GB", "cachetown"), 0)
        s.add(_lead("Cachetown", "GB"))
        s.commit()
        # stale until invalidated
        assert geo_lead_counts(s)["cities"].get(("GB", "cachetown"), 0) == before
        invalidate_geo_counts()
        assert geo_lead_counts(s)["cities"][("GB", "cachetown")] == before + 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_geo_coverage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.geo.coverage'`

- [ ] **Step 3: Implement `app/geo/coverage.py`**

```python
"""Live inventory coverage per geography — the honesty layer of the geo control.

Counts include ONLY leads a buyer could actually be served (not expired, not
opted out, passing serve filters incl. the quality gate). A 60s TTL cache keeps
this cheap; ingestion-sized changes surface within a minute or on invalidate().
"""
from __future__ import annotations

import time

from sqlmodel import Session, select

from app.core.compliance import lead_opted_out
from app.core.db import Lead
from app.core.retention import is_expired
from app.core.serve_filters import passes_serve_filters

_TTL = 60.0
_cache: dict = {"at": 0.0, "data": None}


def invalidate_geo_counts() -> None:
    _cache["at"] = 0.0
    _cache["data"] = None


def geo_lead_counts(session: Session) -> dict:
    now = time.monotonic()
    if _cache["data"] is not None and now - _cache["at"] < _TTL:
        return _cache["data"]
    countries: dict[str, int] = {}
    cities: dict[tuple[str, str], int] = {}
    regions: dict[tuple[str, str], int] = {}
    city_names: dict[str, str] = {}
    for lead in session.exec(select(Lead)).all():
        if is_expired(lead) or lead_opted_out(session, lead):
            continue
        if not passes_serve_filters(session, None, lead, None):
            continue
        cc = (lead.country or "").upper()
        if cc:
            countries[cc] = countries.get(cc, 0) + 1
        if lead.city:
            key = (cc, lead.city.strip().lower())
            cities[key] = cities.get(key, 0) + 1
            city_names.setdefault(lead.city.strip().lower(), lead.city.strip())
        if lead.region:
            rkey = (cc, lead.region.strip().lower())
            regions[rkey] = regions.get(rkey, 0) + 1
    data = {"countries": countries, "cities": cities, "regions": regions,
            "city_names": city_names}
    _cache["at"] = now
    _cache["data"] = data
    return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_geo_coverage.py tests/test_georef.py -v`
Expected: PASS. (If `passes_serve_filters(session, None, ...)` raises on the None buyer id, check `app/core/serve_filters.py` — the quality filter ignores buyer id; if another registered filter requires it, wrap the call per-filter or pass `buyer_account_id=0`. Fix in coverage.py, not in core.)

- [ ] **Step 5: Commit**

```bash
git add app/geo/coverage.py tests/test_geo_coverage.py
git commit -m "feat(geo): honest live coverage counts (serveable leads only, TTL cache)"
```

---

### Task 3: Geo API endpoints + IngestRequest queue

**Files:**
- Create: `app/web/routes_geo.py`
- Modify: `app/core/db.py` (add `IngestRequest` table — generic wording only, no vendor strings)
- Modify: `app/leadvault.py` (include router)
- Modify: `app/web/routes_admin.py` + `app/web/templates/admin_ingest.html` (requested-areas queue)
- Test: `tests/test_geo_routes.py`

**Interfaces:**
- Produces: `GET /app/geo/countries` → `{"countries": [{"code","name","lead_count"}]}` (every reference country; counts honest).
- Produces: `GET /app/geo/areas?country=GB&q=oxf` → `{"groups": [{"label": "England · Oxfordshire", "areas": [{"name","kind","lead_count"}]}], "other": [{"name","lead_count"}]}`. Ranking inside groups: leads desc, then population desc. `other` = inventory cities in that country not matching any reference row (nothing hides).
- Produces: `POST /app/geo/ingest-request` (JSON `{country, area}`, csrf header) → `{"status":"requested"}`; buyer-or-admin; dedupes open requests.
- Produces: `IngestRequest` table: `id, country:str, area:str, requested_by:int (user id), status:str="open", created_at:str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_geo_routes.py
from __future__ import annotations

import re

from fastapi.testclient import TestClient
from sqlmodel import Session, select

import app.leadvault as lv
from app.core.db import IngestRequest


def _client():
    return TestClient(lv.app)


def _token_from(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


def _login(c):
    token = _token_from(c.get("/login").text)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": token}, follow_redirects=False)
    return token


def test_countries_endpoint_lists_all_with_honest_counts():
    c = _client(); _login(c)
    r = c.get("/app/geo/countries")
    assert r.status_code == 200
    by_code = {x["code"]: x for x in r.json()["countries"]}
    assert "FR" in by_code                       # complete: even with 0 leads
    assert by_code["FR"]["lead_count"] == 0      # honest zero, never faked


def test_areas_endpoint_groups_and_counts():
    c = _client(); _login(c)
    r = c.get("/app/geo/areas", params={"country": "GB", "q": "oxford"})
    assert r.status_code == 200
    data = r.json()
    all_areas = [a for g in data["groups"] for a in g["areas"]]
    ox = next(a for a in all_areas if a["name"] == "Oxford")
    assert isinstance(ox["lead_count"], int)     # 0 is fine — must be present + honest
    labels = [g["label"] for g in data["groups"]]
    assert any("Oxfordshire" in l for l in labels)


def test_areas_requires_auth():
    c = _client()
    r = c.get("/app/geo/areas", params={"country": "GB"}, follow_redirects=False)
    assert r.status_code in (302, 303, 401)


def test_ingest_request_created_and_deduped():
    c = _client(); token = _login(c)
    for _ in range(2):
        r = c.post("/app/geo/ingest-request",
                   json={"country": "GB", "area": "Bicester"},
                   headers={"X-CSRF-Token": token})
        assert r.status_code == 200
    with Session(lv.engine) as s:
        rows = s.exec(select(IngestRequest).where(
            IngestRequest.area == "Bicester", IngestRequest.status == "open")).all()
    assert len(rows) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_geo_routes.py -v`
Expected: FAIL with `ImportError: cannot import name 'IngestRequest'`

- [ ] **Step 3: Add `IngestRequest` to `app/core/db.py`**

Add near the other small tables (keep wording generic — this is core):

```python
class IngestRequest(SQLModel, table=True):
    """A queued request to ingest coverage for a named area. Ingestion itself
    remains an admin action; this row only records the ask."""
    id: int | None = Field(default=None, primary_key=True)
    country: str = ""
    area: str = ""
    requested_by: int = 0          # User.id
    status: str = "open"           # open | done | dismissed
    created_at: str = Field(default_factory=_now)
```

- [ ] **Step 4: Implement `app/web/routes_geo.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlmodel import Session, select

from app.core.db import IngestRequest
from app.geo.coverage import geo_lead_counts
from app.geo.ref import list_countries, search_areas
from app.web.csrf import csrf_protect_json
from app.web.deps import get_session, current_user, redirect

router = APIRouter(prefix="/app/geo")


def _authed(request: Request, session: Session):
    u = current_user(request, session)
    return u if u and u.role in ("buyer", "admin") else None


@router.get("/countries")
def countries(request: Request, session: Session = Depends(get_session)):
    if not _authed(request, session):
        return redirect("/login")
    counts = geo_lead_counts(session)["countries"]
    return JSONResponse({"countries": [
        {"code": c.country_code, "name": c.country_name,
         "lead_count": counts.get(c.country_code, 0)}
        for c in list_countries(session)]})


@router.get("/areas")
def areas(request: Request, country: str = "", q: str = "",
          session: Session = Depends(get_session)):
    if not _authed(request, session):
        return redirect("/login")
    cc = (country or "").upper()
    counts = geo_lead_counts(session)
    groups: dict[str, list] = {}
    matched_lower: set[str] = set()
    for row in search_areas(session, cc, q):
        if row.kind == "city":
            n = counts["cities"].get((cc, row.ascii_name.lower()), 0) \
                or counts["cities"].get((cc, row.name.lower()), 0)
            matched_lower.add(row.ascii_name.lower()); matched_lower.add(row.name.lower())
        else:
            n = counts["regions"].get((cc, row.ascii_name.lower()), 0) \
                or counts["regions"].get((cc, row.name.lower()), 0)
        label = " · ".join(x for x in (row.admin1_name, row.admin2_name) if x) \
                or row.country_name
        groups.setdefault(label, []).append(
            {"name": row.name, "kind": row.kind, "lead_count": n,
             "_pop": row.population})
    out_groups = []
    for label, areas_ in groups.items():
        areas_.sort(key=lambda a: (-a["lead_count"], -a.pop("_pop")))
        out_groups.append({"label": label, "areas": areas_})
    out_groups.sort(key=lambda g: -max((a["lead_count"] for a in g["areas"]), default=0))
    # Inventory cities in this country that the reference doesn't know — never hide
    ql = (q or "").strip().lower()
    other = [{"name": counts["city_names"][cl], "lead_count": n}
             for (ccc, cl), n in counts["cities"].items()
             if ccc == cc and cl not in matched_lower
             and (not ql or ql in cl)]
    other.sort(key=lambda a: -a["lead_count"])
    return JSONResponse({"groups": out_groups, "other": other})


@router.post("/ingest-request", dependencies=[Depends(csrf_protect_json)])
async def ingest_request(request: Request, session: Session = Depends(get_session)):
    u = _authed(request, session)
    if not u:
        return Response(status_code=401)
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=400)
    country = (body.get("country") or "").upper().strip()
    area = (body.get("area") or "").strip()
    if not area:
        return Response(status_code=400)
    dup = session.exec(select(IngestRequest).where(
        IngestRequest.country == country, IngestRequest.area == area,
        IngestRequest.status == "open")).first()
    if not dup:
        session.add(IngestRequest(country=country, area=area, requested_by=u.id))
        session.commit()
    return JSONResponse({"status": "requested"})
```

- [ ] **Step 5: Register the router in `app/leadvault.py`**

After `app.include_router(buyer_router)` add:

```python
from app.web.routes_geo import router as geo_router
app.include_router(geo_router)
```

- [ ] **Step 6: Surface the queue on the admin ingest page**

In the `GET /admin/ingest` route in `app/web/routes_admin.py`, add to the template context:

```python
    from app.core.db import IngestRequest
    open_requests = session.exec(select(IngestRequest).where(
        IngestRequest.status == "open").order_by(IngestRequest.created_at)).all()
```
(pass `"open_requests": open_requests` into the context dict)

In `app/web/templates/admin_ingest.html`, above the existing ingest form add:

```html
{% if open_requests %}
{% call ui.card('p-5 mb-6') %}
  <h3 class="text-sm font-semibold text-ink-900 mb-3">Requested areas
    <span class="ml-2">{{ ui.badge(open_requests|length ~ ' open', 'amber') }}</span></h3>
  <table class="w-full text-sm">
    <thead><tr class="text-left text-[11px] uppercase tracking-wider text-ink-400">
      <th class="pb-2">Area</th><th class="pb-2">Country</th><th class="pb-2">Requested</th><th></th></tr></thead>
    <tbody>
    {% for r in open_requests %}
      <tr class="border-t border-slate-100">
        <td class="py-2 font-medium">{{ r.area }}</td>
        <td class="py-2">{{ r.country }}</td>
        <td class="py-2 text-ink-500">{{ r.created_at[:10] }}</td>
        <td class="py-2 text-right">
          <form method="post" action="/admin/ingest-request/{{ r.id }}/close" class="inline">
            <input type="hidden" name="csrf_token" value="{{ csrf }}">
            {{ ui.btn('Mark done', kind='secondary', type='submit') }}
          </form>
        </td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  <p class="mt-2 text-[12.5px] text-ink-500">Run an ingest for a requested area below, then mark it done. Buyers see it as available once leads land.</p>
{% endcall %}
{% endif %}
```

Add the close route in `routes_admin.py` (follow the existing admin POST route pattern with csrf_protect + admin check):

```python
@router.post("/ingest-request/{req_id}/close", dependencies=[Depends(csrf_protect)])
def ingest_request_close(request: Request, req_id: int,
                         session: Session = Depends(get_session)):
    u = _admin(request, session)   # use this file's existing admin-guard helper
    if not u:
        return redirect("/login")
    from app.core.db import IngestRequest
    row = session.get(IngestRequest, req_id)
    if row:
        row.status = "done"
        session.add(row); session.commit()
    return redirect("/admin/ingest")
```

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/test_geo_routes.py tests/ -x -q`
Expected: new tests PASS, full suite green

- [ ] **Step 8: Commit**

```bash
git add app/web/routes_geo.py app/core/db.py app/leadvault.py app/web/routes_admin.py app/web/templates/admin_ingest.html tests/test_geo_routes.py
git commit -m "feat(geo): countries/areas endpoints with honest coverage + ingest-request queue (admin-fulfilled)"
```

---

### Task 4: Generic quality profiles + honest intersection

**Files:**
- Create: `app/quality/profiles/generic.py`
- Create: `app/quality/profiles/combine.py`
- Modify: `app/quality/runtime.py` (register the three)
- Test: `tests/test_quality_profiles_generic.py`

**Interfaces:**
- Produces: registered profile keys `phone_validated`, `email_validated`, `contact_validated`.
- Produces: `app.quality.profiles.combine.combine_profiles(profiles: list[QualityProfile]) -> QualityProfile` — per-field max tier (honest intersection: ALL requirements kept, never one overriding another).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quality_profiles_generic.py
"""Generic channel profiles + honest intersection with campaign profiles.

User requirement: if a campaign requires validated phone AND the buyer picks
"reach by email", the result requires BOTH (fewer leads) — never a silent override.
"""
from __future__ import annotations

import json

from app.core.db import Lead
from app.core.targeting.view import lead_view
from app.quality.gate import clears_gate
from app.quality.profiles.combine import combine_profiles
from app.quality.profiles.registry import get as get_profile
from app.quality.profiles.utilities import UTILITIES


def _view(**val):
    return lead_view(Lead(business_name="X", validation_json=json.dumps(val)))


def test_three_generic_profiles_registered():
    import app.quality.runtime as qr
    qr.register_quality_runtime()
    for key in ("phone_validated", "email_validated", "contact_validated"):
        assert get_profile(key).required


def test_combine_takes_max_tier_per_field_and_unions_fields():
    import app.quality.runtime as qr
    qr.register_quality_runtime()
    combined = combine_profiles([UTILITIES, get_profile("email_validated")])
    assert combined.required["phone"] == "validated"     # from campaign
    assert combined.required["email"] == "validated"     # from channel choice
    assert combined.required["profile"] == "present"


def test_intersection_holds_back_partial_leads():
    """Campaign wants validated phone; buyer picks email channel → need BOTH."""
    import app.quality.runtime as qr
    qr.register_quality_runtime()
    combined = combine_profiles([UTILITIES, get_profile("email_validated")])
    only_email = _view(profile={"tier": "validated"},
                       email={"tier": "validated"}, phone={"tier": "present"})
    only_phone = _view(profile={"tier": "validated"},
                       phone={"tier": "validated"}, email={"tier": "present"})
    both = _view(profile={"tier": "validated"},
                 phone={"tier": "validated"}, email={"tier": "validated"})
    assert clears_gate(only_email, combined) is False
    assert clears_gate(only_phone, combined) is False
    assert clears_gate(both, combined) is True


def test_combine_never_lowers_a_tier():
    import app.quality.runtime as qr
    qr.register_quality_runtime()
    a = get_profile("phone_validated")
    from app.quality.profiles.base import QualityProfile
    weaker = QualityProfile(key="w", label="w", required={"phone": "present"})
    combined = combine_profiles([a, weaker])
    assert combined.required["phone"] == "validated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_quality_profiles_generic.py -v`
Expected: FAIL with `ModuleNotFoundError` (combine / generic)

- [ ] **Step 3: Implement**

`app/quality/profiles/generic.py`:

```python
"""Generic contact-channel profiles the campaign builder maps plain answers onto.
Self-run validation caps at "validated" (INV-Q2) — these never require verified_live."""
from __future__ import annotations

from app.quality.profiles.base import QualityProfile

PHONE_VALIDATED = QualityProfile(
    key="phone_validated", label="Validated phone",
    required={"profile": "present", "phone": "validated"})

EMAIL_VALIDATED = QualityProfile(
    key="email_validated", label="Validated email",
    required={"profile": "present", "email": "validated"})

CONTACT_VALIDATED = QualityProfile(
    key="contact_validated", label="Any validated contact",
    required={"profile": "present", "business_contact": "validated"})
```

`app/quality/profiles/combine.py`:

```python
"""Honest intersection of quality profiles: every requirement from every profile
is kept, at the highest tier any profile demands. Nothing is silently overridden."""
from __future__ import annotations

from app.quality.profiles.base import QualityProfile
from app.quality.tiers import TIER_ORDER


def combine_profiles(profiles: list[QualityProfile]) -> QualityProfile:
    profiles = [p for p in profiles if p is not None]
    if len(profiles) == 1:
        return profiles[0]
    required: dict[str, str] = {}
    weights: dict[str, int] = {}
    for p in profiles:
        for field_, tier in p.required.items():
            cur = required.get(field_)
            if cur is None or TIER_ORDER.index(tier) > TIER_ORDER.index(cur):
                required[field_] = tier
        weights.update(p.weights or {})
    return QualityProfile(
        key="+".join(p.key for p in profiles) or "none",
        label=" + ".join(p.label for p in profiles),
        required=required, weights=weights)
```

In `app/quality/runtime.py`, extend `register_quality_runtime()`:

```python
from app.quality.profiles.generic import PHONE_VALIDATED, EMAIL_VALIDATED, CONTACT_VALIDATED
```
and after `register(UTILITIES)`:
```python
    register(PHONE_VALIDATED)
    register(EMAIL_VALIDATED)
    register(CONTACT_VALIDATED)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_quality_profiles_generic.py tests/test_quality_gate.py tests/test_quality_serve_gate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/quality/profiles/generic.py app/quality/profiles/combine.py app/quality/runtime.py tests/test_quality_profiles_generic.py
git commit -m "feat(quality): generic channel profiles + honest intersection combine (both requirements kept)"
```

---

### Task 5: Answer assembler + campaign prefill

**Files:**
- Create: `app/campaigns/assemble.py`
- Create: `app/campaigns/prefill.py`
- Test: `tests/test_find_assemble.py`

**Interfaces:**
- Produces: `assemble_composition(answers: dict) -> dict` — the ONE path from builder answers to a v2 composition. Answers schema (all keys optional):
  `{"whole_countries": ["GB"], "regions": ["Oxfordshire"], "cities": ["Oxford"], "categories": ["bakery"], "tech_recipes": ["gloriafood"], "min_strength": 1, "contact_channel": "phone|email|either|", "min_quality": 0|50|70|85, "freshness_days": 0|30|90}`
- Produces: `prefill_answers(campaign) -> dict` — same schema, derived by a GENERIC walk of `campaign.composition_template` (INV-8: no per-campaign strings; unfilled `"{placeholders}"` map to empty answers).
- Produces: `channel_profile_key(channel: str) -> str` — `phone→phone_validated`, `email→email_validated`, `either→contact_validated`, else `""`.

Geo semantics: whole-country scopes OR area selections. If both exist → nested `{"op":"OR","nodes":[country_any, region_any/city_any…]}` inside the top AND. Area kinds map to `geo.region_any` / `geo.city_any`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_find_assemble.py
from __future__ import annotations

import json

from sqlmodel import Session

import app.leadvault as lv
from app.campaigns.assemble import assemble_composition, channel_profile_key
from app.campaigns.crud import get_by_key
from app.campaigns.prefill import prefill_answers


def _preds(comp):
    out = []
    def walk(node):
        if "op" in node:
            for n in node.get("nodes", []):
                walk(n)
        else:
            out.append(node["predicate"])
    walk(comp)
    return out


def test_assemble_full_answers():
    comp = assemble_composition({
        "cities": ["Oxford", "Cambridge"], "regions": [],
        "whole_countries": [], "categories": ["restaurant", "cafe"],
        "tech_recipes": ["gloriafood"], "min_strength": 2,
        "contact_channel": "phone", "min_quality": 70, "freshness_days": 30})
    assert comp["op"] == "AND"
    preds = _preds(comp)
    assert "geo.city_any" in preds and "category.any" in preds
    assert "web.runs_tech" in preds and "contactability.has_phone" in preds
    assert "quality.min_score" in preds and "freshness.verified_within" in preds
    tech = next(n for n in comp["nodes"] if n.get("predicate") == "web.runs_tech")
    assert tech["params"] == {"recipe_in": ["gloriafood"], "min_strength": 2}


def test_assemble_mixed_geo_is_or_group():
    comp = assemble_composition({"whole_countries": ["US"], "cities": ["Oxford"],
                                 "regions": [], "categories": [], "tech_recipes": []})
    or_groups = [n for n in comp["nodes"] if n.get("op") == "OR"]
    assert or_groups, "country scope + specific areas must OR together"
    inner = _preds(or_groups[0])
    assert "geo.country_any" in inner and "geo.city_any" in inner


def test_assemble_empty_answers_is_empty_and():
    assert assemble_composition({}) == {"op": "AND", "nodes": []}


def test_channel_profile_key():
    assert channel_profile_key("phone") == "phone_validated"
    assert channel_profile_key("email") == "email_validated"
    assert channel_profile_key("either") == "contact_validated"
    assert channel_profile_key("") == ""


def test_prefill_online_ordering_campaign():
    with Session(lv.engine) as s:
        camp = get_by_key(s, "online_ordering")
    a = prefill_answers(camp)
    assert set(a["tech_recipes"]) == {"gloriafood", "chownow"}
    assert a["contact_channel"] == "either"
    assert a["cities"] == []          # "{area}" placeholder → empty, user fills it


def test_prefill_is_generic_roundtrip():   # INV-8 guard: prefill→assemble covers template intent
    with Session(lv.engine) as s:
        camp = get_by_key(s, "shopify_uk")
    a = prefill_answers(camp)
    assert a["whole_countries"] == ["GB"]
    comp = assemble_composition(a)
    assert "web.runs_tech" in _preds(comp) and "geo.country_any" in _preds(comp)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_find_assemble.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.campaigns.assemble'`

- [ ] **Step 3: Implement `app/campaigns/assemble.py`**

```python
"""assemble_composition — the ONE path from plain-language builder answers to a
v2 composition. The review sentence renders from the OUTPUT of this function,
so what the user reads is always what runs."""
from __future__ import annotations

_CHANNEL_PRED = {"phone": "contactability.has_phone",
                 "email": "contactability.has_role_email",
                 "either": "contactability.has_business_contact"}

_CHANNEL_PROFILE = {"phone": "phone_validated",
                    "email": "email_validated",
                    "either": "contact_validated"}


def channel_profile_key(channel: str) -> str:
    return _CHANNEL_PROFILE.get(channel or "", "")


def _clean(values) -> list[str]:
    return [str(v).strip() for v in (values or []) if str(v).strip()]


def assemble_composition(answers: dict) -> dict:
    nodes: list[dict] = []

    countries = _clean(answers.get("whole_countries"))
    regions = _clean(answers.get("regions"))
    cities = _clean(answers.get("cities"))
    area_nodes: list[dict] = []
    if regions:
        area_nodes.append({"predicate": "geo.region_any", "params": {"in": regions}})
    if cities:
        area_nodes.append({"predicate": "geo.city_any", "params": {"in": cities}})
    country_node = ({"predicate": "geo.country_any", "params": {"in": countries}}
                    if countries else None)
    if country_node and area_nodes:
        nodes.append({"op": "OR", "nodes": [country_node, *area_nodes]})
    elif country_node:
        nodes.append(country_node)
    else:
        nodes.extend(area_nodes)

    categories = _clean(answers.get("categories"))
    if categories:
        nodes.append({"predicate": "category.any", "params": {"in": categories}})

    recipes = _clean(answers.get("tech_recipes"))
    if recipes:
        nodes.append({"predicate": "web.runs_tech",
                      "params": {"recipe_in": recipes,
                                 "min_strength": int(answers.get("min_strength") or 1)}})

    pred = _CHANNEL_PRED.get(answers.get("contact_channel") or "")
    if pred:
        nodes.append({"predicate": pred, "params": {}})

    if int(answers.get("min_quality") or 0) > 0:
        nodes.append({"predicate": "quality.min_score",
                      "params": {"min": int(answers["min_quality"])}})
    if int(answers.get("freshness_days") or 0) > 0:
        nodes.append({"predicate": "freshness.verified_within",
                      "params": {"days": int(answers["freshness_days"])}})
    return {"op": "AND", "nodes": nodes}
```

- [ ] **Step 4: Implement `app/campaigns/prefill.py`**

```python
"""prefill_answers — generic walk of a campaign's composition_template back into
builder answers (INV-8: reads only the row; no per-campaign strings here).
Unfilled "{placeholders}" become empty answers the buyer fills in the builder."""
from __future__ import annotations

import json


def _is_placeholder(v) -> bool:
    return isinstance(v, str) and v.startswith("{") and v.endswith("}") and len(v) > 2


def _clean_list(values) -> list[str]:
    return [v for v in (values or []) if isinstance(v, str) and not _is_placeholder(v)]


def prefill_answers(campaign) -> dict:
    answers = {"whole_countries": [], "regions": [], "cities": [],
               "categories": [], "tech_recipes": [], "min_strength": 1,
               "contact_channel": "", "min_quality": 0, "freshness_days": 0}
    template = json.loads(campaign.composition_template or "{}")

    def walk(node: dict) -> None:
        if "op" in node:
            for n in node.get("nodes", []):
                walk(n)
            return
        pred = node.get("predicate", "")
        params = node.get("params", {}) or {}
        if pred == "geo.country" and not _is_placeholder(params.get("value")):
            answers["whole_countries"].append(params.get("value", ""))
        elif pred == "geo.country_any":
            answers["whole_countries"] += _clean_list(params.get("in"))
        elif pred in ("geo.city", "geo.region"):
            key = "cities" if pred == "geo.city" else "regions"
            if not _is_placeholder(params.get("value")) and params.get("value"):
                answers[key].append(params["value"])
        elif pred == "geo.city_any":
            answers["cities"] += _clean_list(params.get("in"))
        elif pred == "geo.region_any":
            answers["regions"] += _clean_list(params.get("in"))
        elif pred == "category.any":
            answers["categories"] += _clean_list(params.get("in"))
        elif pred == "web.runs_tech":
            answers["tech_recipes"] += _clean_list(params.get("recipe_in"))
            answers["min_strength"] = int(params.get("min_strength") or 1)
        elif pred == "contactability.has_phone":
            answers["contact_channel"] = "phone"
        elif pred == "contactability.has_role_email":
            answers["contact_channel"] = "email"
        elif pred == "contactability.has_business_contact":
            answers["contact_channel"] = "either"
        elif pred == "quality.min_score" and not _is_placeholder(params.get("min")):
            answers["min_quality"] = int(params.get("min") or 0)
        elif pred == "freshness.verified_within" and not _is_placeholder(params.get("days")):
            answers["freshness_days"] = int(params.get("days") or 0)

    walk(template)
    for k in ("whole_countries", "regions", "cities", "categories", "tech_recipes"):
        answers[k] = [x for x in dict.fromkeys(answers[k]) if x]   # dedupe, keep order
    return answers
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_find_assemble.py tests/test_campaign_compile.py -v`
Expected: PASS (compile_campaign untouched)

- [ ] **Step 6: Commit**

```bash
git add app/campaigns/assemble.py app/campaigns/prefill.py tests/test_find_assemble.py
git commit -m "feat(campaigns): generic answer assembler (single composition path) + template prefill walk"
```

---

### Task 6: Deterministic sentence renderer

**Files:**
- Create: `app/campaigns/sentence.py`
- Test: `tests/test_find_sentence.py`

**Interfaces:**
- Consumes: composition dict (output of `assemble_composition`), quality profile keys, fingerprint library (`app.fingerprints.library.get_recipe` for tech labels), `app.geo.ref.list_countries` for country names.
- Produces: `render_sentence(session, composition, quality_profile_keys=()) -> str` — deterministic, plain-language, generated ONLY from the compiled composition + profiles (never from raw user input). Unknown predicates aggregate to "matching N advanced conditions"; negated nodes render "excluding …".

- [ ] **Step 1: Write the failing test**

```python
# tests/test_find_sentence.py
from __future__ import annotations

from sqlmodel import Session

import app.leadvault as lv
from app.campaigns.assemble import assemble_composition
from app.campaigns.sentence import render_sentence


def _s():
    return Session(lv.engine)


def test_sentence_full_campaign():
    comp = assemble_composition({
        "cities": ["Oxford", "Cambridge"], "categories": ["restaurant", "cafe"],
        "tech_recipes": ["gloriafood"], "min_strength": 1,
        "contact_channel": "phone", "freshness_days": 30})
    with _s() as s:
        text = render_sentence(s, comp, quality_profile_keys=["phone_validated"])
    assert text.startswith("We'll find")
    assert "restaurant" in text and "cafe" in text
    assert "GloriaFood" in text                      # label from recipe library
    assert "Oxford or Cambridge" in text
    assert "validated phone" in text
    assert "30 days" in text


def test_sentence_renders_from_composition_not_input():
    """Drift guard: the sentence reflects the COMPILED composition."""
    comp = assemble_composition({"cities": ["Oxford"], "categories": ["bakery"]})
    comp["nodes"] = [n for n in comp["nodes"] if n["predicate"] != "category.any"]
    with _s() as s:
        text = render_sentence(s, comp)
    assert "bakery" not in text                      # dropped node → dropped words


def test_sentence_whole_country_and_unknown_predicates():
    comp = assemble_composition({"whole_countries": ["GB"]})
    comp["nodes"].append({"predicate": "web.is_enriched", "params": {}})
    comp["nodes"].append({"predicate": "source.type", "params": {"value": "open_data"},
                          "negate": True})
    with _s() as s:
        text = render_sentence(s, comp)
    assert "United Kingdom" in text                  # name via geo_ref, not "GB"
    assert "2 advanced condition" in text


def test_sentence_empty_composition():
    with _s() as s:
        text = render_sentence(s, {"op": "AND", "nodes": []})
    assert text == "We'll find all available business leads."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_find_sentence.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.campaigns.sentence'`

- [ ] **Step 3: Implement `app/campaigns/sentence.py`**

```python
"""Deterministic plain-language rendering of a COMPILED composition.

The sentence is generated from the composition that will actually run (plus the
quality profiles that will actually gate), never from raw user input — so the
words cannot drift from the behavior. Order of clauses is fixed."""
from __future__ import annotations

_QUALITY_LABEL = {50: "Good (50+)", 70: "Strong (70+)", 85: "Best (85+)"}

_CHANNEL_TEXT = {"contactability.has_phone": "a phone number",
                 "contactability.has_role_email": "a business email",
                 "contactability.has_business_contact": "a phone or business email"}

_PROFILE_TEXT = {"phone_validated": "a validated phone number",
                 "email_validated": "a validated email address",
                 "contact_validated": "a validated phone or email",
                 "utilities": "a validated phone number",
                 "baseline": ""}


def _join_or(items: list[str]) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " or " + items[-1]


def _country_name(session, code: str) -> str:
    from app.geo.ref import GeoRef
    from sqlmodel import select
    row = session.exec(select(GeoRef).where(
        GeoRef.kind == "country", GeoRef.country_code == code.upper())).first()
    return row.country_name if row else code


def _tech_label(session, recipe_key: str) -> str:
    from app.fingerprints.library import get_recipe
    r = get_recipe(session, recipe_key)
    return r.tech_type if r else recipe_key


def _flat_nodes(composition: dict) -> list[dict]:
    out: list[dict] = []
    def walk(node):
        if "op" in node:
            for n in node.get("nodes", []):
                walk(n)
        else:
            out.append(node)
    walk(composition or {})
    return out


def render_sentence(session, composition: dict, quality_profile_keys=()) -> str:
    nodes = _flat_nodes(composition)
    who, tech, where, extras = [], [], [], []
    contact = ""
    quality = ""
    freshness = ""
    advanced = 0
    excluded = 0

    for node in nodes:
        pred = node.get("predicate", "")
        params = node.get("params", {}) or {}
        if node.get("negate"):
            excluded += 1
            continue
        if pred == "category.any":
            who += [c.replace("_", " ") for c in params.get("in", [])]
        elif pred == "web.runs_tech":
            tech += [_tech_label(session, k) for k in params.get("recipe_in", [])]
            if int(params.get("min_strength") or 1) > 1:
                extras.append(f"with at least {params['min_strength']} confirmed signals")
        elif pred in ("geo.city_any", "geo.region_any"):
            where += list(params.get("in", []))
        elif pred in ("geo.city", "geo.region"):
            if params.get("value"):
                where.append(params["value"])
        elif pred == "geo.country_any":
            where += [f"across {_country_name(session, c)}" for c in params.get("in", [])]
        elif pred == "geo.country":
            if params.get("value"):
                where.append(f"across {_country_name(session, params['value'])}")
        elif pred in _CHANNEL_TEXT:
            contact = _CHANNEL_TEXT[pred]
        elif pred == "quality.min_score":
            quality = _QUALITY_LABEL.get(int(params.get("min") or 0),
                                         f"{params.get('min')}+")
        elif pred == "freshness.verified_within":
            freshness = f"verified within the last {params.get('days')} days"
        else:
            advanced += 1

    for key in quality_profile_keys or ():
        t = _PROFILE_TEXT.get(key)
        if t:
            contact = t          # gate text (validated …) supersedes presence text

    subject = _join_or(sorted(set(who))) + " businesses" if who else "businesses"
    parts = [f"We'll find {subject}" if who else "We'll find all available business leads"
             if not (tech or where or contact or quality or freshness or advanced or excluded)
             else f"We'll find {subject}"]
    if tech:
        parts.append(f"that run {_join_or(sorted(set(tech)))} on their website")
    if extras:
        parts.append(_join_or(extras))
    if where:
        plain = [w for w in where if not w.startswith("across ")]
        scoped = [w for w in where if w.startswith("across ")]
        loc = _join_or(plain)
        if loc:
            parts.append(f"in {loc}")
        if scoped:
            parts.append(("or " if loc else "") + _join_or(scoped))
    if contact:
        parts.append(f"with {contact}")
    if quality:
        parts.append(f"at quality {quality}")
    if freshness:
        parts.append(freshness)
    if advanced:
        parts.append(f"matching {advanced} advanced condition{'s' if advanced != 1 else ''}")
    if excluded:
        parts.append(f"excluding {excluded} condition{'s' if excluded != 1 else ''}")
    return ", ".join([parts[0]] + parts[1:]) + "."
```

- [ ] **Step 4: Run tests, adjust wording only in the module until green**

Run: `python -m pytest tests/test_find_sentence.py -v`
Expected: PASS. (The empty-composition branch must return exactly `We'll find all available business leads.` — note the period comes from the final join; verify and fix the branch so the literal matches.)

- [ ] **Step 5: Commit**

```bash
git add app/campaigns/sentence.py tests/test_find_sentence.py
git commit -m "feat(campaigns): deterministic plain-language sentence rendered from compiled composition"
```

---

### Task 7: /app/find routes — page, compile, estimate (multi-profile), save, aliases

**Files:**
- Create: `app/web/routes_find.py`
- Modify: `app/leadvault.py` (include router)
- Modify: `app/web/routes_buyer.py` (estimate accepts `quality_profile_keys` list — shared helper)
- Test: `tests/test_find_routes.py`

**Interfaces:**
- Produces: `GET /app/find` — renders `find.html` with context: `campaigns` (active list), `countries` (list of `{code,name,lead_count}`), `cat_options` (list of `{key, count}`), `tech_groups` (recipes grouped by category: `{category: [{recipe_key, tech_type, confidence, enabled}]}`), `quality_options`, `mode` (`guided|quick` from `?mode=`), `preset` (composition JSON when `?audience=<segment_id>`), `prefill` (answers JSON + campaign meta when `?campaign=<key>`), `csrf`, `credits`.
- Produces: `POST /app/find/compile` (csrf JSON) — body `{"campaign_key": "", "answers": {...}}` → `{"composition", "sentence", "quality_profile_keys", "gated_notices", "scoring_profile_key"}`.
- Produces: `POST /app/find/estimate` (csrf JSON) — like composer estimate but accepts `"quality_profile_keys": [..]` (combined via `combine_profiles`); single `quality_profile_key` still accepted.
- Produces: `POST /app/find/save` (form) — saves Segment, redirects `/app/audiences`.
- Keeps: `/app/composer/estimate` and `/app/composer/apply-campaign` working unchanged (they stay in routes_buyer.py; estimate logic is refactored into a shared function both call).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_find_routes.py
from __future__ import annotations

import re

from fastapi.testclient import TestClient

import app.leadvault as lv


def _client():
    return TestClient(lv.app)


def _token_from(html):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


def _login(c):
    token = _token_from(c.get("/login").text)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": token}, follow_redirects=False)
    return token


def test_find_page_renders_campaigns_and_modes():
    c = _client(); _login(c)
    r = c.get("/app/find")
    assert r.status_code == 200
    assert "Utilities (UK)" in r.text
    assert "Describe your own" in r.text
    assert "Quick search" in r.text
    # buyer-facing copy: no engine jargon
    assert "min_score" not in r.text
    assert "predicate" not in r.text.lower() or "data-" in r.text  # allow data attrs only


def test_find_compile_custom_answers():
    c = _client(); token = _login(c)
    r = c.post("/app/find/compile", json={"answers": {
        "cities": ["Oxford"], "categories": ["bakery"],
        "contact_channel": "phone", "freshness_days": 30}},
        headers={"X-CSRF-Token": token})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sentence"].startswith("We'll find")
    assert "validated phone" in data["sentence"]
    preds = [n.get("predicate") for n in data["composition"]["nodes"]]
    assert "geo.city_any" in preds
    assert data["quality_profile_keys"] == ["phone_validated"]
    assert data["gated_notices"] == []


def test_find_compile_campaign_carries_profile_and_gates():
    c = _client(); token = _login(c)
    r = c.post("/app/find/compile", json={
        "campaign_key": "business_restructuring",
        "answers": {"cities": ["Oxford"], "categories": ["bakery"],
                    "contact_channel": "email"}},
        headers={"X-CSRF-Token": token})
    assert r.status_code == 200
    data = r.json()
    assert data["gated_notices"], "gated financial signals must be surfaced"
    assert all("attributes." not in str(n.get("params", {}))
               for n in data["composition"]["nodes"])   # INV-6: never in composition
    # campaign profile + channel profile both present (honest intersection downstream)
    assert "email_validated" in data["quality_profile_keys"]


def test_find_estimate_accepts_profile_list():
    c = _client(); token = _login(c)
    r = c.post("/app/find/estimate", json={
        "composition": {"op": "AND", "nodes": []},
        "quality_profile_keys": ["utilities", "email_validated"]},
        headers={"X-CSRF-Token": token})
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"count", "score_distribution", "freshness_distribution", "samples"}


def test_old_composer_estimate_still_works():
    c = _client(); _login(c)
    r = c.post("/app/composer/estimate", json={
        "composition": {"op": "AND", "nodes": []},
        "quality_profile_key": "baseline"})
    assert r.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_find_routes.py -v`
Expected: FAIL (404 on /app/find)

- [ ] **Step 3: Refactor shared estimate + implement `app/web/routes_find.py`**

In `app/web/routes_buyer.py`, extract the body of `composer_estimate` (after auth/body parse) into a module-level helper so both routers share one implementation:

```python
def run_estimate(session, buyer_account_id, body: dict):
    """Shared estimate: resolves 1..n quality profile keys (honest intersection)."""
    composition = body.get("composition") or {"op": "AND", "nodes": []}
    keys = body.get("quality_profile_keys")
    if not keys:
        single = body.get("quality_profile_key", "") or ""
        keys = [single] if single else []
    profiles = []
    from app.quality.profiles.registry import get as get_quality_profile
    for k in keys:
        try:
            profiles.append(get_quality_profile(k))
        except KeyError:
            pass                       # unknown key → skipped, baseline still gates
    ctx = None
    if profiles:
        from app.quality.profiles.combine import combine_profiles
        ctx = {"quality_profile": combine_profiles(profiles)}
    from app.core.targeting.estimate import estimate as targeting_estimate
    return targeting_estimate(session, buyer_account_id, composition,
                              sample=int(body.get("sample", 9)), ctx=ctx)
```

`composer_estimate` keeps its route, auth, segment-audit block, and error handling, but calls `run_estimate(session, u.buyer_account_id, body)`.

New `app/web/routes_find.py`:

```python
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlmodel import Session, select, func

from app.campaigns.assemble import assemble_composition, channel_profile_key
from app.campaigns.crud import list_active, get_by_key
from app.campaigns.prefill import prefill_answers
from app.campaigns.sentence import render_sentence
from app.core.compliance import audit
from app.core.db import LeadCategoryLink
from app.core.purchasing import balance
from app.core.targeting.segments import create_segment, get_owned
from app.geo.coverage import geo_lead_counts
from app.geo.ref import list_countries
from app.web.csrf import ensure_csrf, csrf_protect, csrf_protect_json
from app.web.deps import templates, get_session, current_user, redirect
from app.web.routes_buyer import run_estimate

router = APIRouter(prefix="/app")


def _buyer(request: Request, session: Session):
    u = current_user(request, session)
    if not u or u.role != "buyer":
        return None
    return u


def _category_counts(session: Session) -> list[dict]:
    rows = session.exec(
        select(LeadCategoryLink.category_key, func.count(LeadCategoryLink.lead_id))
        .group_by(LeadCategoryLink.category_key)).all()
    return sorted(({"key": k, "count": n} for k, n in rows), key=lambda x: x["key"])


def _tech_groups(session: Session) -> dict[str, list[dict]]:
    from app.fingerprints.library import list_recipes
    groups: dict[str, list[dict]] = {}
    for r in list_recipes(session):
        groups.setdefault(r.category, []).append({
            "recipe_key": r.recipe_key, "tech_type": r.tech_type,
            "confidence": r.confidence, "enabled": r.enabled})
    for g in groups.values():
        g.sort(key=lambda x: (not x["enabled"], x["tech_type"]))
    return dict(sorted(groups.items()))


@router.get("/find")
def find_page(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    counts = geo_lead_counts(session)["countries"]
    ctx: dict = {
        "request": request, "user": u, "csrf": ensure_csrf(request),
        "credits": balance(session, u.buyer_account_id),
        "campaigns": list_active(session),
        "countries": [{"code": c.country_code, "name": c.country_name,
                       "lead_count": counts.get(c.country_code, 0)}
                      for c in list_countries(session)],
        "cat_options": _category_counts(session),
        "tech_groups": _tech_groups(session),
        "mode": request.query_params.get("mode", "guided"),
        "prefill": None, "preset": None,
    }
    campaign_key = request.query_params.get("campaign", "")
    if campaign_key:
        camp = get_by_key(session, campaign_key)
        if camp:
            ctx["prefill"] = json.dumps({
                "campaign_key": camp.key, "name": camp.name,
                "description": camp.description,
                "answers": prefill_answers(camp),
                "gated_notices": json.loads(camp.gated_signals or "[]")})
            audit(session, u.id, "campaign.select", "Campaign", camp.key,
                  {"key": camp.key, "phase": "find_page_load"})
    audience_id = request.query_params.get("audience", "")
    if audience_id:
        try:
            seg = get_owned(session, int(audience_id), u.buyer_account_id)
            if seg:
                ctx["preset"] = seg.composition_json
        except (ValueError, TypeError):
            pass
    from app.core.targeting.composer import predicate_options
    ctx["options"] = predicate_options(session)      # advanced disclosure data
    from app.fingerprints import library as fp_library
    ctx["tech_recipes"] = fp_library.list_recipes(session)
    return templates.TemplateResponse(request, "find.html", ctx)


@router.post("/find/compile", dependencies=[Depends(csrf_protect_json)])
async def find_compile(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return Response(status_code=401)
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=400)
    answers = body.get("answers") or {}
    campaign_key = body.get("campaign_key", "") or ""

    composition = assemble_composition(answers)
    quality_keys: list[str] = []
    gated_notices: list[dict] = []
    scoring_profile_key = ""
    if campaign_key:
        camp = get_by_key(session, campaign_key)
        if not camp:
            return Response(status_code=404)
        if camp.quality_profile_key:
            quality_keys.append(camp.quality_profile_key)
        gated_notices = [{"path": p, "reason": "requires licensed source"}
                         for p in json.loads(camp.gated_signals or "[]")]
        scoring_profile_key = camp.scoring_profile_key
    ck = channel_profile_key(answers.get("contact_channel", ""))
    if ck and ck not in quality_keys:
        quality_keys.append(ck)

    sentence = render_sentence(session, composition, quality_profile_keys=quality_keys)
    import hashlib
    comp_hash = hashlib.sha256(
        json.dumps(composition, sort_keys=True).encode()).hexdigest()[:16]
    audit(session, u.id, "find.compile", "Campaign", campaign_key or "custom",
          {"composition_hash": comp_hash})
    return JSONResponse({"composition": composition, "sentence": sentence,
                         "quality_profile_keys": quality_keys,
                         "gated_notices": gated_notices,
                         "scoring_profile_key": scoring_profile_key})


@router.post("/find/estimate", dependencies=[Depends(csrf_protect_json)])
async def find_estimate(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return Response(status_code=401)
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=400)
    try:
        return run_estimate(session, u.buyer_account_id, body)
    except (ValueError, KeyError, TypeError):
        return Response(status_code=400)


@router.post("/find/save", dependencies=[Depends(csrf_protect)])
async def find_save(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    form = await request.form()
    name = form.get("name", "").strip() or "Untitled audience"
    try:
        composition = json.loads(form.get("composition", "{}"))
    except (json.JSONDecodeError, TypeError):
        composition = {"op": "AND", "nodes": []}
    create_segment(session, u.buyer_account_id, name, composition,
                   origin_key=form.get("origin_key", "") or "")
    return redirect("/app/audiences")
```

Register in `app/leadvault.py` after the geo router:

```python
from app.web.routes_find import router as find_router
app.include_router(find_router)
```

NOTE: `find.html` doesn't exist yet — for THIS task create a minimal placeholder so route tests pass; Task 8 builds the real page:

```html
{% extends "base.html" %}
{% import "components.html" as ui %}
{% block heading %}Find leads{% endblock %}
{% block body %}
<div data-page="find">
  <p>Quick search</p><p>Describe your own</p>
  {% for c in campaigns %}<p>{{ c.name }}</p>{% endfor %}
</div>
{% endblock %}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_find_routes.py tests/test_campaign_routes.py tests/test_targeting_estimate.py -v`
Expected: PASS (old endpoints untouched)

- [ ] **Step 5: Commit**

```bash
git add app/web/routes_find.py app/web/routes_buyer.py app/leadvault.py app/web/templates/find.html tests/test_find_routes.py
git commit -m "feat(find): /app/find routes - compile (sentence+profiles+gates), estimate w/ profile intersection, save"
```

---

### Task 8: The find page UI — stepper, geo control, business types, quality bar, review, results, quick mode

**Files:**
- Modify: `app/web/templates/find.html` (replace the Task-7 placeholder with the real page)
- Create: `app/web/templates/_find_advanced.html` (advanced targeting disclosure — extracted from composer.html's advanced panel)
- Create: `app/static/find.js`
- Modify: `app/web/templates/components.html` (new macros: `stepper`, `coverage_badge`)
- Modify: `app/main.py` or wherever static files are mounted — verify `/static` is already served (composer uses app/static/app.js? check `app/static/index.html` usage; if templates inline JS instead, inline find.js in find.html the same way composer.html does)
- Test: `tests/test_find_page.py`

**Interfaces:**
- Consumes: Task 7 context + endpoints; Task 3 geo endpoints.
- Produces: the complete buyer journey UI. All copy plain-language. Every control has a label + helper. Empty/zero/loading/error states designed.

**Layout contract (from the approved design preview):**
- Header: mode tabs `Campaigns (guided)` | `Quick search` — plus a stepper rail (1 Campaign · 2 Where · 3 Who · 4 Quality bar · 5 Review & run) shown in guided mode.
- **Step 1:** campaign template cards (name, description, honesty badge: green "Ready today" or amber "Some traits need a licensed source" derived from gated_signals) + a "Describe your own" card. Selecting one loads prefill answers and advances.
- **Step 2 (Where):** two-pane geo control. Left: country list (search box; each row: name + `coverage_badge`). Right: area search within selected country; grouped rows (group label = "England · Oxfordshire") with checkbox, name, coverage badge; "not yet ingested" rows greyed with a "Request this area" ghost button (fires POST /app/geo/ingest-request, then shows "Requested ✓"); chips for selections; "Whole country" toggle per selected country (mutually exclusive with that country's area chips — enforce in JS); "Other areas in inventory" group when the API returns `other`.
- **Step 3 (Who):** grouped searchable multi-select: "Business categories" (from `cat_options`, each with count) and per-category tech groups from `tech_groups` (enabled recipes selectable with green "strong signal" badge when confidence == "high"; disabled recipes greyed, unselectable, "test before use" label). Selected state = checkmark + chip. Prefilled gated notices render as amber locked rows "requires licensed source".
- **Step 4 (Quality bar):** three radio groups — "How will you reach them?" (Phone / Email / Either / No requirement), "Lead quality" (Any / Good / Strong / Best), "How recently verified?" (Any time / 30 days / 90 days). Helper text explains what Validated means (format+line-type; syntax+MX) and shows a locked "Verified-live — requires licensed provider" row (never selectable).
- **Step 5 (Review & run):** calls `/app/find/compile` → renders the sentence in a brand-tinted box + gated notices; live estimate via `/app/find/estimate` (count, score bands as "Best/Strong/Good/Low", freshness bands, masked sample cards via a JS renderer matching `ui.lead_card` fields); "Edit targeting (advanced)" `<details>` disclosure containing `_find_advanced.html`; Run button reveals the results grid (estimate with `sample: 60`, cards get Unlock buttons posting to `/app/unlock/{lead_id}`); "Save as audience" form posts to `/app/find/save`.
- **Quick mode (`?mode=quick` or tab):** steps 2–4 controls rendered as one form column + results immediately on the right; same components, same endpoints.
- **Zero state honesty:** when estimate count is 0, show empty state: "No leads match yet. Areas marked 'not yet ingested' have no coverage — try an area with leads, or request ingestion." Never show sample cards on 0.
- Footer line: `Geographic reference data © GeoNames (CC BY 4.0). Lead data: see per-lead provenance.`

**JS state (single source in find.js):**
```js
const state = {
  mode: 'guided', step: 1,
  campaignKey: '', answers: {
    whole_countries: [], regions: [], cities: [],
    categories: [], tech_recipes: [], min_strength: 1,
    contact_channel: 'either', min_quality: 0, freshness_days: 0,
  },
  compiled: null,          // {composition, sentence, quality_profile_keys, gated_notices}
  advancedComposition: null, // when the advanced disclosure edits the composition directly
};
```
Flow: any answer change → debounce 350ms → POST compile → store → POST estimate → render. If `advancedComposition` is set (user edited advanced), estimate uses it and the sentence panel shows "Advanced targeting active — the summary below reflects your edited targeting" with the sentence re-rendered by compile on the edited composition (send `{"answers": null, "composition": ...}`? NO — compile only takes answers. Instead: advanced editing keeps predicates as the source; call `/app/find/estimate` with the edited composition, and render the sentence by calling compile with the CURRENT answers PLUS display a badge "edited in advanced mode"; the run/save always uses the edited composition. Keep it simple and honest: when advanced edits exist, the sentence box is replaced by the plain list of active conditions from the advanced panel labels.)

- [ ] **Step 1: Write the failing test (server-rendered content only)**

```python
# tests/test_find_page.py
from __future__ import annotations

import re

from fastapi.testclient import TestClient

import app.leadvault as lv


def _client():
    return TestClient(lv.app)


def _login(c):
    m = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text)
    token = m.group(1)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": token}, follow_redirects=False)
    return token


def test_find_page_has_stepper_and_steps():
    c = _client(); _login(c)
    html = c.get("/app/find").text
    for label in ("Campaign", "Where", "Who", "Quality bar", "Review"):
        assert label in html
    assert "Whole country" in html
    assert "not yet ingested" in html.lower() or "data-zero-copy" in html  # zero-state copy present


def test_find_page_verified_live_always_locked():   # INV-Q2 in the UI
    c = _client(); _login(c)
    html = c.get("/app/find").text
    assert "Verified-live" in html
    assert "requires licensed provider" in html
    m = re.search(r'<[^>]*data-tier-locked[^>]*>', html)
    assert m, "Verified-live must be a locked row (data-tier-locked), never an input"


def test_find_page_greyed_recipes_not_selectable():   # INV-13 in the UI
    c = _client(); _login(c)
    html = c.get("/app/find").text
    # disabled recipes render with data-recipe-disabled and no checkbox input
    if "data-recipe-disabled" in html:
        seg = html.split("data-recipe-disabled", 1)[1][:300]
        assert "<input" not in seg.split(">", 1)[1][:200]


def test_find_page_no_engine_jargon():
    c = _client(); _login(c)
    html = c.get("/app/find").text
    visible = re.sub(r'<script.*?</script>', '', html, flags=re.S)
    visible = re.sub(r'data-[a-z-]+="[^"]*"', '', visible)
    assert "min_score" not in visible
    assert "quality.min" not in visible
    assert "geo.city_any" not in visible


def test_quick_mode_renders():
    c = _client(); _login(c)
    r = c.get("/app/find", params={"mode": "quick"})
    assert r.status_code == 200
    assert "Quick search" in r.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_find_page.py -v`
Expected: FAIL (placeholder page lacks stepper labels)

- [ ] **Step 3: Add macros to `components.html`**

```html
{% macro stepper(steps, current) %}
<div class="flex flex-wrap gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2.5 shadow-card" data-stepper>
  {% for s in steps %}
  <button type="button" data-step-btn="{{ loop.index }}"
    class="flex items-center gap-2 rounded-full px-3 py-1.5 text-[12.5px] font-medium transition
      {{ 'bg-brand-50 text-brand-800' if loop.index == current else 'text-ink-400 hover:text-ink-600' }}">
    <span class="grid h-5 w-5 place-items-center rounded-full text-[10.5px] font-bold
      {{ 'bg-brand-600 text-white' if loop.index == current else 'bg-slate-100 text-ink-500' }}"
      data-step-num>{{ loop.index }}</span>{{ s }}
  </button>
  {% endfor %}
</div>
{% endmacro %}

{% macro coverage_badge(count) %}
  {% if count and count > 0 %}
    <span class="rounded-full bg-brand-100 px-2 py-0.5 text-[11px] font-semibold text-brand-800 tabular-nums">{{ count }} lead{{ 's' if count != 1 }}</span>
  {% else %}
    <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-ink-400">0 — not yet ingested</span>
  {% endif %}
{% endmacro %}
```

- [ ] **Step 4: Build `find.html`, `_find_advanced.html`, `find.js`**

This is the largest step. Follow the layout contract above exactly. Concrete requirements the reviewer will check:

1. `find.html` extends base.html, imports components as `ui`, uses `ui.stepper(['Campaign','Where','Who','Quality bar','Review & run'], 1)`, and renders all five step panels as `<section data-step-panel="N" class="hidden">` toggled by JS (panel 1 visible initially in guided mode; quick mode shows a single combined form + results and hides the stepper).
2. The geo control fetches `/app/geo/countries` on first open of step 2 and `/app/geo/areas?country=CC&q=...` on selection/typing (debounced 250ms). Render EXACTLY the honest badge semantics from `coverage_badge` (JS re-creates the same classes; keep a `<template id="tpl-coverage-has">`/`tpl-coverage-none` pair in the HTML so classes live in one place).
3. Zero-lead area rows: greyed text (`text-ink-400`), still selectable checkbox, plus a "Request this area" ghost button → POST `/app/geo/ingest-request` with `X-CSRF-Token` from `window._csrf` (set `<script>window._csrf = "{{ csrf }}";</script>` in find.html); after 200 → replace button with `Requested ✓` (idempotent server-side). Add `data-zero-copy` on the copy block that explains 0-lead areas so tests can find it.
4. Business-type control: server-renders the full grouped list (categories from `cat_options` with counts; tech groups from `tech_groups`), client-side filter box, checkbox rows with visible checkmarks, chips summary. Disabled recipes: `data-recipe-disabled`, `opacity-60`, NO `<input>`, label suffix `test before use` (use `ui.badge('test before use','neutral')`). High-confidence enabled recipes get `ui.badge('strong signal','green')`.
5. Quality step: radios named `contact_channel` (`phone|email|either|`), `min_quality` (`0|50|70|85` labeled Any/Good (50+)/Strong (70+)/Best (85+)), `freshness_days` (`0|30|90`). Locked row: `<div data-tier-locked class="...opacity-70 border-dashed">🔒 Verified-live — requires licensed provider</div>` with helper "Only a licensed verification provider can confirm a mailbox or line is live. We never claim it ourselves." No input inside.
6. Review step: sentence box (brand-50 bg), gated notices (amber rows, lock icon, "requires licensed source"), estimate panel (count, Best/Strong/Good/Low bars mapped from `score_distribution` keys `85-100/70-84/50-69/0-49`, freshness bars, sample cards). Sample cards in JS use fields from `mask_preview` (`category_keys, city, score_total, price_credits, has_phone, has_email, has_website, reason, lead_id`) and reuse the same card classes as `ui.lead_card`. On `count == 0`: render `ui.empty_state`-equivalent markup with the honest copy from the layout contract; NO cards.
7. Run: sets `sample: 60`, renders the results grid with Unlock forms (`POST /app/unlock/{lead_id}` with csrf hidden input). "Save as audience": name input + hidden `composition` + `origin_key` (campaign key or `""`) posting `/app/find/save`.
8. `_find_advanced.html`: port the advanced panel from `composer.html` lines ~166–365 (predicate rows with enable checkbox, params inputs per `params_schema`, negate toggle, coverage % text, sparse group, tech recipe rows + min-strength slider) — markup only, wired to find.js functions `advReadComposition()` / `advLoadComposition(comp)`. Include it inside `<details data-advanced>` with summary "Edit targeting (advanced)". When any advanced input changes: `state.advancedComposition = advReadComposition()`; the sentence box swaps to a "Custom targeting (edited in advanced mode)" list of the active condition labels; estimate/run/save use `state.advancedComposition`.
9. Every fetch has error handling: non-200 → inline error banner "Something went wrong — try again" (use `ui.banner` classes); loading states: skeleton pulse on estimate panel (`animate-pulse`).
10. Footer: `<p class="mt-10 text-[11.5px] text-ink-400">Geographic reference © <a href="https://www.geonames.org" class="underline">GeoNames</a> (CC BY 4.0) · Lead data licensing shown per lead.</p>`
11. Inline `find.js` at the end of find.html via `<script src="/static/find.js"></script>` if `/static` is mounted in `app/leadvault.py` / `app/main.py`; verify with `grep -n "StaticFiles" app -r`. If NOT mounted, inline the entire JS in a `<script>` block at the end of find.html (composer.html precedent). Either is acceptable; do not add a new mount just for this.
12. Prefill/preset bootstrapping at load: `window._prefill = {{ prefill|safe if prefill else 'null' }}; window._preset = {{ preset|safe if preset else 'null' }};` — prefill fills `state.answers` + campaign banner and jumps to step 2; preset loads `state.advancedComposition` and jumps to step 5 (review).

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_find_page.py tests/test_find_routes.py -v`
Expected: PASS

- [ ] **Step 6: Manual smoke in dev server**

Run: `python -m uvicorn app.leadvault:app --port 8000` (background), open http://127.0.0.1:8000/login → buyer@demo.local / buyer12345 → /app/find. Click through all five steps with devtools console open — zero JS errors is the bar. Kill the server after.

- [ ] **Step 7: Commit**

```bash
git add app/web/templates/find.html app/web/templates/_find_advanced.html app/web/templates/components.html app/static/find.js tests/test_find_page.py
git commit -m "feat(find): full guided journey UI - stepper, honest geo control, grouped business types, quality bar, review/estimate/results, quick mode"
```

---

### Task 9: Saved audiences (merge Segments + legacy Recipes)

**Files:**
- Create: `app/web/templates/audiences.html`
- Modify: `app/web/routes_find.py` (audiences page + delete)
- Test: `tests/test_audiences.py`

**Interfaces:**
- Produces: `GET /app/audiences` — lists Segments (name, created_at, Open → `/app/find?audience=<id>`, Delete) and legacy LeadRecipe rows read-only under "Older saved searches" (name only, with note "saved from the old search — open Find leads to rebuild"). `POST /app/audiences/{id}/delete` deletes an owned segment.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_audiences.py
from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient
from sqlmodel import Session

import app.leadvault as lv
from app.core.db import LeadRecipe


def _client():
    return TestClient(lv.app)


def _login(c):
    m = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text)
    token = m.group(1)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": token}, follow_redirects=False)
    return token


def test_audiences_lists_segments_and_legacy_recipes():
    c = _client(); token = _login(c)
    c.post("/app/find/save", data={"csrf_token": token, "name": "Aud One",
                                   "composition": json.dumps({"op": "AND", "nodes": []}),
                                   "origin_key": ""}, follow_redirects=False)
    with Session(lv.engine) as s:
        from app.core.db import BuyerAccount, User
        from sqlmodel import select
        u = s.exec(select(User).where(User.email == "buyer@demo.local")).first()
        s.add(LeadRecipe(buyer_account_id=u.buyer_account_id, name="Old Recipe",
                         filters_json="{}", scoring_profile_key=""))
        s.commit()
    html = c.get("/app/audiences").text
    assert "Aud One" in html
    assert "Old Recipe" in html
    assert "/app/find?audience=" in html


def test_audience_delete_owned_only():
    c = _client(); token = _login(c)
    c.post("/app/find/save", data={"csrf_token": token, "name": "Aud Two",
                                   "composition": json.dumps({"op": "AND", "nodes": []}),
                                   "origin_key": ""}, follow_redirects=False)
    html = c.get("/app/audiences").text
    m = re.search(r'/app/audiences/(\d+)/delete', html)
    assert m
    r = c.post(f"/app/audiences/{m.group(1)}/delete", data={"csrf_token": token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "Aud Two" not in c.get("/app/audiences").text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_audiences.py -v`
Expected: FAIL (404)

- [ ] **Step 3: Implement routes (append to `app/web/routes_find.py`)**

```python
@router.get("/audiences")
def audiences_page(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    from app.core.targeting.segments import list_segments
    from app.core.db import LeadRecipe
    segs = list_segments(session, u.buyer_account_id)
    legacy = session.exec(select(LeadRecipe).where(
        LeadRecipe.buyer_account_id == u.buyer_account_id)).all()
    return templates.TemplateResponse(request, "audiences.html", {
        "request": request, "user": u, "segments": segs, "legacy": legacy,
        "csrf": ensure_csrf(request)})


@router.post("/audiences/{segment_id}/delete", dependencies=[Depends(csrf_protect)])
def audience_delete(request: Request, segment_id: int,
                    session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    from app.core.targeting.segments import delete_segment
    delete_segment(session, segment_id, u.buyer_account_id)
    return redirect("/app/audiences")
```

- [ ] **Step 4: Build `audiences.html`** — segments.html structure as base, design-system styled: `ui.page_intro('Saved audiences', 'Re-run a saved targeting any time — opening one lands on Review & run with everything loaded.')`; a card per segment (name, created date, `ui.btn('Open', href='/app/find?audience=' ~ s.id, kind='secondary')`, Delete danger button in a form); legacy section only when `legacy` non-empty, each row `ui.badge('legacy','neutral')` + note "saved from the old search — open Find leads to rebuild it"; `ui.empty_state('No saved audiences yet', 'Build targeting in Find leads and click "Save as audience".')` when both empty.

- [ ] **Step 5: Run tests + commit**

Run: `python -m pytest tests/test_audiences.py -v` → PASS

```bash
git add app/web/templates/audiences.html app/web/routes_find.py tests/test_audiences.py
git commit -m "feat(find): saved audiences page merging segments + legacy recipes (read-only)"
```

---

### Task 10: Navigation + old-route redirects + retire old pages

**Files:**
- Modify: `app/web/templates/base.html` (nav)
- Modify: `app/web/routes_buyer.py` (old page routes become redirects; JSON endpoints stay)
- Delete: `app/web/templates/marketplace.html`, `campaigns.html`, `campaign_preview.html`, `recipes.html`, `segments.html`, `composer.html` (AFTER redirects land; `_find_advanced.html` already carries the advanced markup)
- Test: `tests/test_route_migration.py`

**Interfaces:**
- Produces: nav = Dashboard / **Find leads** (`/app/find`) / **Saved audiences** (`/app/audiences`) + Manage section unchanged.
- Produces: 303 redirects — `/app/marketplace → /app/find?mode=quick`; `POST /app/marketplace/search → /app/find?mode=quick`; `/app/campaigns → /app/find`; `/app/campaign-preview → /app/find`; `/app/composer → /app/find` (carrying `?campaign=` / `?segment=` → `?audience=`); `/app/recipes (GET+POST) → /app/audiences`; `/app/segments → /app/audiences`; `POST /app/segments/{id}/delete → kept working` (redirect target updated) or forwarded to the audiences delete.
- Keeps: `POST /app/composer/estimate`, `POST /app/composer/apply-campaign`, `POST /app/composer/save` (now redirecting to `/app/audiences` on success).
- Also: `POST /app/ack` success redirect target changes from `/app/marketplace` to `/app/find`; unlock error redirect `/app/marketplace` → `/app/find`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_route_migration.py
"""Old bookmarks must land somewhere sensible — never 404 mid-session."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

import app.leadvault as lv


def _client():
    return TestClient(lv.app)


def _login(c):
    m = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text)
    token = m.group(1)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": token}, follow_redirects=False)
    return token


def _assert_redirect(c, path, expect_prefix, method="get", token=""):
    if method == "get":
        r = c.get(path, follow_redirects=False)
    else:
        r = c.post(path, data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code in (301, 302, 303, 307, 308), f"{path} -> {r.status_code}"
    assert r.headers["location"].startswith(expect_prefix), \
        f"{path} -> {r.headers['location']}"


def test_all_old_routes_redirect():
    c = _client(); token = _login(c)
    _assert_redirect(c, "/app/marketplace", "/app/find")
    _assert_redirect(c, "/app/campaigns", "/app/find")
    _assert_redirect(c, "/app/campaign-preview", "/app/find")
    _assert_redirect(c, "/app/composer", "/app/find")
    _assert_redirect(c, "/app/recipes", "/app/audiences")
    _assert_redirect(c, "/app/segments", "/app/audiences")
    _assert_redirect(c, "/app/marketplace/search", "/app/find", method="post", token=token)


def test_composer_redirect_carries_params():
    c = _client(); _login(c)
    r = c.get("/app/composer?campaign=utilities_uk", follow_redirects=False)
    assert "campaign=utilities_uk" in r.headers["location"]
    r = c.get("/app/composer?segment=7", follow_redirects=False)
    assert "audience=7" in r.headers["location"]


def test_json_endpoints_still_alive():
    c = _client(); token = _login(c)
    r = c.post("/app/composer/estimate",
               json={"composition": {"op": "AND", "nodes": []}})
    assert r.status_code == 200
    r = c.post("/app/composer/apply-campaign",
               json={"key": "utilities_uk", "params": {"area": "Oxford"}},
               headers={"X-CSRF-Token": token})
    assert r.status_code == 200


def test_nav_has_no_old_tabs():
    c = _client(); _login(c)
    html = c.get("/app/find").text
    assert 'href="/app/marketplace"' not in html
    assert 'href="/app/composer"' not in html
    assert 'href="/app/campaigns"' not in html
    assert 'href="/app/find"' in html
    assert 'href="/app/audiences"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_route_migration.py -v`
Expected: FAIL (old pages render 200)

- [ ] **Step 3: Convert old page routes in `routes_buyer.py` to redirects**

Replace the BODIES of `marketplace_page`, `marketplace_search`, `campaigns_page`, `campaign_preview`, `recipes_page`, `recipes_save`, `segments_page`, and `composer_page` (keep auth guard lines):

```python
@router.get("/marketplace")
def marketplace_page(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    return redirect("/app/find?mode=quick")
```

`marketplace_search` (POST): same redirect (keep the csrf dependency so stale forms don't 403 confusingly? No — REMOVE the csrf dependency on this stub: a stale bookmark POST should still land on the new page, and the stub performs no state change).

`composer_page`:

```python
@router.get("/composer")
def composer_page(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    campaign = request.query_params.get("campaign", "")
    segment = request.query_params.get("segment", "")
    if campaign:
        return redirect(f"/app/find?campaign={campaign}")
    if segment:
        return redirect(f"/app/find?audience={segment}")
    return redirect("/app/find")
```

`campaigns_page` / `campaign_preview` → `redirect("/app/find")`. `recipes_page` / `recipes_save` / `segments_page` → `redirect("/app/audiences")`. `segment_delete` stays functional but its final redirect becomes `/app/audiences`. `composer_save` final redirect becomes `/app/audiences`. In `ack_submit` change `redirect("/app/marketplace")` → `redirect("/app/find")`; in `unlock` change the error redirect `/app/marketplace` → `/app/find`. Remove the now-unused imports (`search`, `estimate` from `app.core.marketplace`, `DEFAULT_FILTERS`, `_filters_from_form` if unused) — run the full suite to catch import fallout in other tests; where old tests exercised the removed marketplace form flow (e.g. `tests/test_marketplace.py` posts the search form and asserts result HTML), UPDATE those tests to assert the redirect instead of deleting them; keep `app/core/marketplace.py` itself (admin/estimate may use `search`; check callers with grep first).

- [ ] **Step 4: Update the nav in `base.html`**

Replace lines 74–78 (buyer "Find leads" block) with:

```html
        {{ nav('/app','Dashboard', ic.home) }}
        {{ nav('/app/find','Find leads', ic.target) }}
        {{ nav('/app/audiences','Saved audiences', ic.grid) }}
```

- [ ] **Step 5: Delete retired templates**

```bash
git rm app/web/templates/marketplace.html app/web/templates/campaigns.html app/web/templates/campaign_preview.html app/web/templates/recipes.html app/web/templates/segments.html app/web/templates/composer.html
```

Then grep for references: `grep -rn "marketplace.html\|composer.html\|campaigns.html\|segments.html\|recipes.html\|campaign_preview" app tests` — every hit must be gone or updated (route stubs no longer render templates).

- [ ] **Step 6: Run FULL suite; fix fallout**

Run: `python -m pytest tests/ -q`
Expected: failures ONLY in tests that asserted old pages render (e.g. `test_marketplace.py`, `test_campaign_routes.py::test_campaigns_page_lists_both_campaigns`, `test_web_journey.py`). Update each to the new reality: page asserts move to `/app/find` (campaign names now render there), form-flow asserts become redirect asserts. Do NOT weaken JSON endpoint tests. Re-run until green.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(nav): one entry point - Find leads + Saved audiences; old routes redirect, JSON aliases kept, old templates retired"
```

---

### Task 11: Per-lead quality tier visibility

**Files:**
- Modify: `app/core/masking.py` (`mask_preview` + `unlock_view` expose per-field tiers + match strength — no raw contact data in previews)
- Modify: `app/web/templates/components.html` (`tier_chip`, `quality_chips` macros; `lead_card` gains chips)
- Modify: `app/web/templates/lead_detail.html`, `app/web/templates/purchased.html` (expanded quality view)
- Modify: `app/static/find.js` / find.html JS card renderer (tier chips on sample/result cards)
- Test: `tests/test_quality_visibility.py`

**Interfaces:**
- Produces: `mask_preview(lead)` gains `"quality": {"phone": {"tier","line_type"}, "email": {"tier"}, "address": {"tier"}, "website": {"tier"}, "profile": {"tier"}}` and `"tech_match": {"recipe_key": str, "strength": int} | None` (from `attributes_json` keys `recipe_key`/`match_strength` when present). Tiers only — NEVER phone/email values (masking safety test below).
- Produces: `unlock_view(lead)` gains the same `quality` + `tech_match` keys.
- Produces: chip rendering rule (single source of truth for copy):
  - `validated` → green chip `✓✓ {Field} — Validated` with meaning suffix: phone `(format + line type)`, email `(syntax + MX)`, address `(geocoded)`, website `(reachable)`.
  - `present` → neutral chip `✓ {Field} — Present`.
  - `absent` → omitted from cards; on detail pages a subdued `— {Field} not yet available`.
  - ALWAYS one locked chip: `🔒 Verified-live — requires licensed provider` (dashed border, `data-tier-locked`). Never render "Verified" for validated data (INV-Q2).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quality_visibility.py
from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient
from sqlmodel import Session

import app.leadvault as lv
from app.core.db import Lead
from app.core.masking import mask_preview


def _lead(**kw):
    v = {"profile": {"tier": "validated"},
         "phone": {"tier": "validated", "line_type": "fixed_line"},
         "email": {"tier": "present"},
         "address": {"tier": "present"},
         "website": {"tier": "validated"}}
    defaults = dict(business_name="Vis Bakery", city="Cambridge", country="GB",
                    phone="+441223000000", public_email="hello@visbakery.example",
                    category_keys_json='["bakery"]',
                    validation_json=json.dumps(v),
                    attributes_json=json.dumps({"recipe_key": "gloriafood",
                                                "match_strength": 3}))
    defaults.update(kw)
    return Lead(**defaults)


def test_mask_preview_exposes_tiers_never_values():
    p = mask_preview(_lead())
    assert p["quality"]["phone"]["tier"] == "validated"
    assert p["quality"]["phone"]["line_type"] == "fixed_line"
    assert p["quality"]["email"]["tier"] == "present"
    assert p["tech_match"] == {"recipe_key": "gloriafood", "strength": 3}
    blob = json.dumps(p)
    assert "+441223000000" not in blob          # masking holds
    assert "visbakery.example" not in blob


def test_mask_preview_never_shows_verified_live_from_self_run():   # INV-Q2
    lead = _lead()
    p = mask_preview(lead)
    assert all(f.get("tier") != "verified_live" for f in p["quality"].values())


def test_lead_detail_renders_tiers_and_locked_verified():
    with Session(lv.engine) as s:
        lead = _lead()
        s.add(lead); s.commit(); s.refresh(lead)
        lead_id = lead.id
    c = TestClient(lv.app)
    m = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": m.group(1)}, follow_redirects=False)
    # own the lead so detail renders (insert PurchasedLead directly)
    from app.core.db import PurchasedLead, User
    from sqlmodel import select
    with Session(lv.engine) as s:
        u = s.exec(select(User).where(User.email == "buyer@demo.local")).first()
        s.add(PurchasedLead(buyer_account_id=u.buyer_account_id, lead_id=lead_id,
                            price_paid_credits=1))
        s.commit()
    html = c.get(f"/app/purchased/{lead_id}").text
    assert "Validated" in html
    assert "format + line type" in html
    assert "Verified-live" in html and "requires licensed provider" in html
    assert "data-tier-locked" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_quality_visibility.py -v`
Expected: FAIL with `KeyError: 'quality'`

- [ ] **Step 3: Extend `app/core/masking.py`**

Add a module-level helper and wire it into both views:

```python
_QUALITY_FIELDS = ("phone", "email", "address", "website", "profile")


def _quality_summary(lead: Lead) -> dict:
    """Per-field validation tiers for display. Tiers only — never contact values.
    Self-run validation caps at 'validated'; verified_live only ever arrives via a
    licensed provider stamp, so passing tiers through cannot overclaim."""
    v = json.loads(lead.validation_json or "{}")
    out = {}
    for f in _QUALITY_FIELDS:
        fb = v.get(f) or {}
        entry = {"tier": fb.get("tier", "absent")}
        if f == "phone" and fb.get("line_type"):
            entry["line_type"] = fb["line_type"]
        out[f] = entry
    return out


def _tech_match(lead: Lead) -> dict | None:
    attrs = json.loads(lead.attributes_json or "{}")
    if attrs.get("recipe_key"):
        return {"recipe_key": attrs["recipe_key"],
                "strength": int(attrs.get("match_strength") or 1)}
    return None
```

In `mask_preview` add to the returned dict: `"quality": _quality_summary(lead), "tech_match": _tech_match(lead),` — same two keys in `unlock_view`.

- [ ] **Step 4: Add macros + render chips**

`components.html`:

```html
{% macro tier_chip(field_label, info, meaning='') %}
  {% set t = info.tier if info else 'absent' %}
  {% if t == 'validated' %}
    <span class="inline-flex items-center gap-1.5 rounded-lg border border-brand-100 bg-brand-50 px-2.5 py-1 text-[12px] font-medium text-brand-800">✓✓ {{ field_label }} — Validated{% if meaning %} <span class="text-brand-700/70">· {{ meaning }}</span>{% endif %}</span>
  {% elif t == 'present' %}
    <span class="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-[12px] font-medium text-ink-600">✓ {{ field_label }} — Present</span>
  {% endif %}
{% endmacro %}

{% macro quality_chips(q, tech=None, detail=False) %}
<div class="flex flex-wrap gap-1.5">
  {{ tier_chip('Phone', q.phone, ('format + line type' ~ (' (' ~ q.phone.line_type|replace('_',' ') ~ ')' if q.phone.line_type is defined and q.phone.line_type else ''))) }}
  {{ tier_chip('Email', q.email, 'syntax + MX') }}
  {{ tier_chip('Address', q.address, 'geocoded') }}
  {{ tier_chip('Website', q.website, 'reachable') }}
  <span data-tier-locked class="inline-flex items-center gap-1.5 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-2.5 py-1 text-[12px] font-medium text-ink-400">🔒 Verified-live — requires licensed provider</span>
</div>
{% if detail %}
  {% for f, label in [('phone','Phone'),('email','Email'),('address','Address'),('website','Website')] %}
    {% if q[f].tier == 'absent' %}<p class="mt-1 text-[12px] text-ink-400">— {{ label }} not yet available</p>{% endif %}
  {% endfor %}
{% endif %}
{% if tech %}
  <p class="mt-2 flex items-center gap-2 text-[12.5px] text-ink-600">Tech match: <b>{{ tech.recipe_key }}</b>
    <span class="inline-flex gap-0.5">{% for i in range(5) %}<i class="h-1.5 w-3.5 rounded-full {{ 'bg-brand-500' if i < tech.strength else 'bg-slate-200' }}"></i>{% endfor %}</span>
    {{ tech.strength }} signal{{ 's' if tech.strength != 1 }} confirmed on their own homepage</p>
{% endif %}
{% endmacro %}
```

In `lead_card`, replace the badge row (lines 90–94) with `{{ quality_chips(c.quality, c.tech_match) }}` (keep a `{% if c.quality is defined %}` guard falling back to the old badges for callers not yet passing quality). In `lead_detail.html` and `purchased.html` add a "Contact quality" section calling `{{ ui.quality_chips(lead.quality, lead.tech_match, detail=True) }}` (purchased rows: compact — reuse chips in the row detail link target only if the table gets crowded; detail page is required, table chips optional). In find.js's card renderer, replicate the chip markup from the two `<template>` tags (`tpl-tier-validated`, `tpl-tier-present`, `tpl-tier-locked`) added to find.html so classes stay single-sourced.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_quality_visibility.py tests/test_masking.py tests/ -q`
Expected: green (update `test_masking.py` expectations if they assert exact dict keys)

- [ ] **Step 6: Commit**

```bash
git add app/core/masking.py app/web/templates/components.html app/web/templates/lead_detail.html app/web/templates/purchased.html app/web/templates/find.html app/static/find.js tests/test_quality_visibility.py
git commit -m "feat(quality): per-lead tier chips (Present/Validated, locked Verified-live) + fingerprint match strength"
```

---

### Task 12: Geo grep-clean + attribution

**Files:**
- Create: `tests/test_geo_grepclean.py`
- Modify: `README.md` (data sources / attribution section)

- [ ] **Step 1: Write the test (mirrors `tests/test_quality_grepclean.py` style — read that file first and copy its walking pattern)**

```python
# tests/test_geo_grepclean.py
"""INV: app/core stays generic — geo reference vendor strings must not leak in."""
from __future__ import annotations

import pathlib
import re

CORE = pathlib.Path(__file__).resolve().parents[1] / "app" / "core"
PATTERN = re.compile(r"geonames", re.IGNORECASE)


def test_core_free_of_geo_vendor_strings():
    offenders = []
    for py in CORE.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        if PATTERN.search(text):
            offenders.append(str(py))
    assert not offenders, f"geo vendor strings leaked into core: {offenders}"


def test_core_does_not_import_geo_package():
    offenders = []
    for py in CORE.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"from app\.geo|import app\.geo", text):
            offenders.append(str(py))
    assert not offenders, f"core must not depend on app.geo: {offenders}"
```

- [ ] **Step 2: Run — must already pass (design keeps geo out of core); if it fails, fix the leak, not the test**

Run: `python -m pytest tests/test_geo_grepclean.py -v`
Expected: PASS

- [ ] **Step 3: README attribution**

In README.md's data/licensing section add:

```markdown
- **Geographic reference:** country/region/city reference data derived from
  [GeoNames](https://www.geonames.org) (CC BY 4.0). Used only to render the area
  selector; lead coverage counts always come from actual inventory.
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_geo_grepclean.py README.md
git commit -m "test(geo): grep-clean core of geo vendor strings + GeoNames CC BY 4.0 attribution"
```

---

### Task 13: Full-suite pass + polish sweep

- [ ] **Step 1:** `python -m pytest tests/ -q` — everything green.
- [ ] **Step 2:** Grep sweep for leftovers: `grep -rn "app/marketplace\|app/composer\|app/campaigns\|app/segments\|app/recipes" app/web/templates app/static` — only the alias JSON endpoints and redirect stubs may reference old paths.
- [ ] **Step 3:** Jargon sweep on rendered pages (find, audiences, purchased, lead detail, dashboard): no `min_score`, no predicate keys, no "composition" in visible copy.
- [ ] **Step 4:** Commit any fixes: `git commit -am "chore(find): post-build polish sweep"`.

---

### Task 14: Browser verification (orchestrator, Playwright MCP) — REQUIRED before review handoff

Start the app (`python -m uvicorn app.leadvault:app --port 8000`), then verify IN THE BROWSER, capturing screenshots:

1. **Login** as buyer@demo.local → lands on dashboard; sidebar shows exactly: Dashboard, Find leads, Saved audiences, Purchased leads, Suppression, Billing & credits.
2. **Guided journey:** Find leads → pick "Online ordering upgrades" → prefilled tech recipes visible with "strong signal" badges → Where: select United Kingdom → search "oxf" → Oxford shows a real count badge; a 0-lead town shows "0 — not yet ingested" greyed + "Request this area" → select Oxford + Cambridge → Who: category counts visible; a greyed recipe is NOT clickable → Quality bar: pick Phone; locked Verified-live row visible → Review: sentence reads correctly and mentions validated phone; estimate count + distributions + masked samples render (no full contact data anywhere) → Run: results grid with Unlock buttons → Save as audience.
3. **Honest zero:** select ONLY a 0-lead area → estimate shows 0, empty-state copy, NO sample cards.
4. **Quick search:** mode tab → single form → results.
5. **Advanced disclosure:** open "Edit targeting (advanced)", toggle a predicate, estimate updates, review panel flags custom targeting.
6. **Saved audience reopen:** Saved audiences → Open → lands on Review with targeting loaded.
7. **OLD-ROUTE REDIRECTS (user-required):** navigate directly to `/app/marketplace`, `/app/composer`, `/app/composer?campaign=utilities_uk`, `/app/campaigns`, `/app/campaign-preview`, `/app/recipes`, `/app/segments` — each lands on the new pages, logged-in session intact, never a 404.
8. **Quality visibility:** unlock a lead → purchased detail shows tier chips with meanings + locked Verified-live + tech match pips (for a fingerprint lead).
9. **Admin:** login as admin → Ingestion page shows the requested-area queue (file one via buyer first); Mark done works.
10. **Console:** zero JS errors across the whole pass.

Fix anything found (each fix: test first where testable, commit).

---

### Task 15: Whole-branch review

Run the code-review skill over the whole branch diff (`git diff master-start..HEAD` scope), apply confirmed findings, re-run the suite, then STOP and hand to the user for review with: summary of what changed, spec deltas (see header), screenshots from Task 14, and the test count.

## Self-Review (done at plan-writing time)

- Spec coverage: IA/nav (T7,8,10), geo two-layer + honesty + ingest requests (T1–3), business types (T7,8), builder + sentence + compile (T5–7), quality profiles + intersection [user add #1] (T4), tier visibility (T11), polish (T8,13), invariants/grep-clean (T12 + tests throughout), redirects incl. browser check [user add #2] (T10, T14.7), audiences merge (T9), attribution (T12).
- Type consistency: `assemble_composition(answers)` / `prefill_answers(campaign)` / `channel_profile_key(channel)` / `render_sentence(session, composition, quality_profile_keys)` / `combine_profiles(list)` / `run_estimate(session, buyer_account_id, body)` / `geo_lead_counts(session)` — names match across tasks.
- Known judgment calls left to implementers (documented in-task): serve_filters None-buyer handling (T2 S4), static mount vs inline JS (T8 S4.11), masking test-key updates (T11 S5).
