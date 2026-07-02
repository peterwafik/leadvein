# Targeting v2 — Plan 2: Data-Driven Composer UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use `- [ ]`.

> 🛑 **INTENDED STOPPING POINT (survives context resets):** build this composer → then the **Campaign
> layer** (per-campaign defaults + quality profile threaded through the gate) → **THEN a real
> demand test on utilities-UK with real buyers.** Do NOT keep building past the Campaign layer without
> putting it in front of real buyers. Pause after THIS plan for user review before the Campaign layer.
> **Payments stay PARKED.**

**Goal:** A data-driven Targeting composer — buyers build a filter composition from options that reflect
**real inventory**, see a **live estimate + masked results**, and **save Segments** — wired to the
FINISHED Plan-1 engine (evaluator/estimate/Segments/quality gate). Guided by default, full control in an
Advanced view. No mocked controls; unavailable predicates are honestly greyed.

**Architecture:** A maintained `lv_attribute_coverage` rollup (populated normalized-view paths, updated
at ingest) drives which predicate controls appear. The composer posts a composition (v2 JSON) to a
gate-enforced estimate endpoint that reuses the built `estimate()` + `matching_by_composition`. Segments
use the built `Segment` CRUD. Core stays generic (registry + coverage); concrete predicate strings stay
in `app/targeting`.

**Tech Stack:** Python 3.11 (`.venv/Scripts/python`), FastAPI/SQLModel, Jinja + Tailwind (the shipped
design system: `base.html` + `components.html`), pytest. Reuses `lead_view`, predicate `registry`,
`matching_by_composition`, `estimate`, `Segment` CRUD, `serve_filters`/quality gate.

## Global Constraints
- Interpreter `.venv/Scripts/python`; tests `.venv/Scripts/python -m pytest`. Bash for git; no `cd`. Do
  NOT commit `*.db`. Conftest uses a temp DB; the pilot `leadvault.db` may be held by a running server —
  do NOT `rm` it; the suite doesn't need it.
- **Data-driven, never hardcoded:** every option (cities, categories, predicates) comes from the
  registry + the coverage rollup of what's populated in inventory; lists grow as inventory is ingested.
- **Guided + advanced (spec §6):** guided = a small curated default set; Advanced = the full available
  predicate catalog. Both. Never dump everything on one screen; never hide the full set.
- **Wired to the real engine — no mocks:** every control maps to a registered predicate with the built
  evaluator behind it. Predicates whose signals aren't populated are shown **disabled/greyed** with an
  honest note. Nothing faked in front of a missing engine.
- **INV-1..INV-5 (targeting) + INV-Q1 (quality gate) hold in the composer paths:** a lead that fails the
  quality gate is NOT surfaced at composer search, preview/estimate, OR unlock. Tests REQUIRED that prove
  the composer respects the gate (not only the baseline search).
- **INV-Q/grep-clean core:** `grep -rinE "energy|utility|osm|overpass|campaign|provider|mca|lender|quality" app/core/`
  → empty. Composer core pieces are generic; concrete predicate strings live in `app/targeting`.
- Masking / suppression / opt-out / retention / ODbL attribution / audit unchanged. TDD; frequent commits.

---

## File Structure
```
app/core/db.py                         # + AttributeCoverage (lv_attribute_coverage)
app/core/targeting/coverage.py         # TRACKED_PATHS(registry), recompute_coverage, populated_paths, coverage_pct
app/core/targeting/composer.py         # available_predicates / unavailable_predicates (registry × coverage) — generic
app/ingestion/pipeline.py              # recompute_coverage after an ingest batch
app/web/routes_buyer.py                # /app/composer (GET), /app/composer/estimate (POST json), /app/composer/save (POST), /app/segments (GET)
app/web/templates/composer.html        # guided + advanced builder, live estimate, masked results, save
app/web/templates/segments.html        # saved segments list
app/web/routes_admin.py                # /admin/recompute-coverage (backfill button)
tests/test_targeting_coverage.py test_targeting_composer.py test_composer_gate.py test_composer_grepclean.py
```

---

### Task 1: Coverage rollup — model, recompute, populated paths

**Files:** Modify `app/core/db.py`; Create `app/core/targeting/coverage.py`; Modify
`app/ingestion/pipeline.py`; Test `tests/test_targeting_coverage.py`.

**Interfaces — Produces:** `AttributeCoverage` (`lv_attribute_coverage`: `path` unique+indexed,
`populated` int, `total` int, `updated_at`). `TRACKED_PATHS() -> list[str]` (union of every registered
predicate's `reads`). `recompute_coverage(session) -> int` (scan leads via `lead_view`+`get_path`, upsert
per-path populated/total counts; returns #paths). `populated_paths(session, min_count=1) -> set[str]`.
`coverage_pct(session, path) -> float`.

- [ ] **Step 1: Failing test** (`tests/test_targeting_coverage.py`)
```python
import json
from sqlmodel import Session
from app.core.db import init_db, Lead, _now
from app.core.leadcats import sync_lead_categories
from app.core.targeting import registry
from app.targeting.runtime import register_targeting_runtime
from app.core.targeting.coverage import (recompute_coverage, populated_paths, coverage_pct,
                                         TRACKED_PATHS)


def _seed(s):
    a = Lead(business_name="A", country="GB", city="Oxford", phone="1", score_total=80,
             category_keys_json=json.dumps(["cafe"]), date_last_verified=_now(),
             intent_json=json.dumps({"ssl": True}))
    b = Lead(business_name="B", country="GB", city="", phone="", score_total=40,
             category_keys_json=json.dumps(["gym"]), intent_json="{}")
    for x in (a, b):
        s.add(x)
    s.commit()
    for x in (a, b):
        s.refresh(x); sync_lead_categories(s, x)


def test_coverage_reflects_real_inventory():
    registry.clear(); register_targeting_runtime()
    e = init_db("sqlite://")
    with Session(e) as s:
        _seed(s)
        assert "country" in TRACKED_PATHS()            # union of predicate reads
        recompute_coverage(s)
        pp = populated_paths(s)
        assert "country" in pp and "city" in pp and "phone" in pp   # A has these
        assert "intent.ssl" in pp                                   # A has it
        # 2 leads, both country=GB -> 100%; city populated on 1 of 2 -> 50%
        assert coverage_pct(s, "country") == 100.0
        assert coverage_pct(s, "city") == 50.0
```
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement.** `app/core/db.py` add:
```python
class AttributeCoverage(SQLModel, table=True):
    __tablename__ = "lv_attribute_coverage"
    id: int | None = Field(default=None, primary_key=True)
    path: str = Field(default="", index=True)
    populated: int = 0
    total: int = 0
    updated_at: str = Field(default_factory=_now)
```
`app/core/targeting/coverage.py`:
```python
from __future__ import annotations
from sqlmodel import Session, select, delete
from app.core.db import Lead, AttributeCoverage, _now
from app.core.targeting import registry
from app.core.targeting.view import lead_view, get_path, MISSING


def TRACKED_PATHS() -> list[str]:
    paths = set()
    for k in registry.all_keys():
        paths.update(registry.get(k).reads)
    return sorted(paths)


def _populated(view, path) -> bool:
    v = get_path(view, path)
    return v is not MISSING and v not in (None, "", [], {})


def recompute_coverage(session: Session) -> int:
    leads = session.exec(select(Lead)).all()
    total = len(leads)
    paths = TRACKED_PATHS()
    counts = {p: 0 for p in paths}
    for l in leads:
        v = lead_view(l)
        for p in paths:
            if _populated(v, p):
                counts[p] += 1
    session.exec(delete(AttributeCoverage))
    for p, n in counts.items():
        session.add(AttributeCoverage(path=p, populated=n, total=total, updated_at=_now()))
    session.commit()
    return len(paths)


def populated_paths(session: Session, min_count: int = 1) -> set:
    return {r.path for r in session.exec(select(AttributeCoverage).where(
        AttributeCoverage.populated >= min_count)).all()}


def coverage_pct(session: Session, path: str) -> float:
    r = session.exec(select(AttributeCoverage).where(AttributeCoverage.path == path)).first()
    if not r or not r.total:
        return 0.0
    return round(r.populated / r.total * 100, 1)
```
`app/ingestion/pipeline.py`: at the END of `ingest()` (after the loop, before returning counts), add
`from app.core.targeting.coverage import recompute_coverage` and `recompute_coverage(session)` so the
rollup is refreshed at ingest time (NOT per-builder-load).
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `feat(targeting): attribute-coverage rollup (recompute at ingest; populated paths + %)`

---

### Task 2: Data-driven available predicates

**Files:** Create `app/core/targeting/composer.py`; Test `tests/test_targeting_composer.py`.

**Interfaces — Produces:** `predicate_options(session) -> {"available":[desc...], "unavailable":[desc...]}`
where `desc = {"key","group","label","params_schema","coverage_pct":dict-of-reads-to-pct}`. A predicate
is **available** iff every path in its `reads` is in `populated_paths(session)`; else **unavailable**
(for greyed display). Both lists grouped-friendly (include `group`). Generic — reads the registry +
coverage only; no concrete predicate strings.

- [ ] **Step 1: Failing test**
```python
import json
from sqlmodel import Session
from app.core.db import init_db, Lead, _now
from app.core.leadcats import sync_lead_categories
from app.core.targeting import registry
from app.targeting.runtime import register_targeting_runtime
from app.core.targeting.coverage import recompute_coverage
from app.core.targeting.composer import predicate_options


def test_options_are_data_driven():
    registry.clear(); register_targeting_runtime()
    e = init_db("sqlite://")
    with Session(e) as s:
        lead = Lead(business_name="A", country="GB", city="Oxford", phone="1", score_total=80,
                    category_keys_json=json.dumps(["cafe"]), date_last_verified=_now(),
                    intent_json="{}")   # NOTE: no intent signals populated
        s.add(lead); s.commit(); s.refresh(lead); sync_lead_categories(s, lead)
        recompute_coverage(s)
        opt = predicate_options(s)
        avail = {d["key"] for d in opt["available"]}
        unavail = {d["key"] for d in opt["unavailable"]}
        assert "geo.country" in avail and "geo.city" in avail and "quality.min_score" in avail
        # web.has_signal reads "intent" which is NOT populated -> unavailable (greyed), not faked
        assert "web.has_signal" in unavail
        assert avail.isdisjoint(unavail)
```
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement `app/core/targeting/composer.py`**
```python
from __future__ import annotations
from app.core.targeting import registry
from app.core.targeting.coverage import populated_paths, coverage_pct


def _desc(session, p) -> dict:
    return {"key": p.key, "group": p.group, "label": p.label,
            "params_schema": p.params_schema,
            "coverage_pct": {r: coverage_pct(session, r) for r in p.reads}}


def predicate_options(session) -> dict:
    pop = populated_paths(session)
    available, unavailable = [], []
    for k in registry.all_keys():
        p = registry.get(k)
        (available if set(p.reads) <= pop else unavailable).append(_desc(session, p))
    return {"available": available, "unavailable": unavailable}
```
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `feat(targeting): data-driven predicate options (available vs greyed, from coverage)`

---

### Task 3: Gate-enforced composer estimate endpoint (INV-Q1)

**Files:** Modify `app/web/routes_buyer.py`; Test `tests/test_composer_gate.py`.

**Interfaces — Produces:** `POST /app/composer/estimate` (buyer-auth + csrf) accepting a JSON body
`{"composition": <v2 composition>, "sample": int?}`, returning JSON
`{"count", "score_distribution", "freshness_distribution", "samples":[masked...]}` by calling the BUILT
`estimate(session, buyer_account_id, composition)`. The built `estimate()` already applies the quality
serve-gate + suppression/opt-out/expiry + `mask_preview` — so INV-Q1 holds here by construction; the test
proves it.

- [ ] **Step 1: Failing test** (`tests/test_composer_gate.py`)
```python
import json, pytest
from fastapi.testclient import TestClient
from sqlmodel import Session
import app.leadvault as lv
from app.core.db import Lead, BuyerAccount, User, _now
from app.core.leadcats import sync_lead_categories
from app.core.purchasing import grant_credits
from tests.quality_helpers import hot_validation_json

def _hot(s, city):
    l = Lead(business_name="Hot", category_keys_json=json.dumps(["cafe"]), city=city, phone="1",
             score_total=90, date_last_verified=_now(), price_credits=3,
             validation_json=hot_validation_json())
    s.add(l); s.commit(); s.refresh(l); sync_lead_categories(s, l); return l

def _cold(s, city):  # blob-less -> fails the quality gate
    l = Lead(business_name="Cold", category_keys_json=json.dumps(["cafe"]), city=city, phone="1",
             score_total=90, date_last_verified=_now(), price_credits=3, validation_json="{}")
    s.add(l); s.commit(); s.refresh(l); sync_lead_categories(s, l); return l

def test_composer_estimate_respects_quality_gate():   # INV-Q1 through the composer
    c = TestClient(lv.app)
    c.post("/login", data={"email":"buyer@demo.local","password":"buyer12345"})  # add csrf per test_csrf pattern
    with Session(lv.engine) as s:
        _hot(s, "Composerville"); _cold(s, "Composerville")
    comp = {"op":"AND","nodes":[{"predicate":"geo.city","params":{"value":"Composerville"}}]}
    r = c.post("/app/composer/estimate", json={"composition": comp})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1                       # only the HOT lead — cold held back by the gate
    assert "Cold" not in json.dumps(data["samples"]) and "Hot" not in json.dumps(data["samples"])  # masked
```
(Follow the CSRF pattern used in `tests/test_csrf.py` / `test_billing.py` to obtain a token for the POST;
for a JSON endpoint you may exempt it from csrf_protect OR send the token — match how other buyer POSTs
handle it. The gate assertion is the point.)
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement the route in `app/web/routes_buyer.py`:**
```python
@router.post("/composer/estimate")
async def composer_estimate(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return Response(status_code=401)
    body = await request.json()
    composition = body.get("composition") or {"op": "AND", "nodes": []}
    from app.core.targeting.estimate import estimate as targeting_estimate
    est = targeting_estimate(session, u.buyer_account_id, composition,
                             sample=int(body.get("sample", 9)))
    return est
```
(`targeting.estimate` returns a plain dict → FastAPI serializes it as JSON. It already applies
`passes_serve_filters` + suppression/opt-out/expiry + `mask_preview`. This endpoint is buyer-gated; it is
read-only (no state change) so it does not require CSRF — but confirm the app's CSRF setup does not force
it; if it does, exempt this read-only JSON route explicitly.)
- [ ] **Step 4: Run — PASS.** Then `.venv/Scripts/python -m pytest tests/test_composer_gate.py -q`.
- [ ] **Step 5: Commit** `feat(targeting): gate-enforced composer estimate endpoint (INV-Q1 in composer path)`

---

### Task 4: The composer UI (guided + advanced, live estimate, masked results)

**Files:** Create `app/web/templates/composer.html`; Modify `app/web/routes_buyer.py` (GET `/app/composer`),
`app/web/templates/base.html` (nav: replace the "Campaigns · Preview" link target OR add a "Composer"
entry — keep the preview reachable too). Test: covered by Task 3 + a render smoke in Task 6.

**Interfaces — Consumes:** `predicate_options(session)`, `_inventory_options(session)` (cities), the
`/app/composer/estimate` endpoint, `ensure_csrf`. **Produces:** `GET /app/composer` rendering the builder.

- [ ] **Step 1: Add the route**
```python
@router.get("/composer")
def composer_page(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    from app.core.targeting.composer import predicate_options
    return templates.TemplateResponse(request, "composer.html", {
        "request": request, "user": u, "csrf": ensure_csrf(request),
        "options": predicate_options(session), "credits": balance(session, u.buyer_account_id),
        **_inventory_options(session)})
```
- [ ] **Step 2: Build `app/web/templates/composer.html`** — extends `base.html`, imports `components.html`.
  Requirements (match the shipped design system + the marketplace exemplar for style):
  - Two modes via a toggle: **Guided** (default) and **Advanced**.
    - **Guided:** a small curated set of controls — Area (city datalist from `cities`), Business types
      (chips from available category options), Lead quality (select). These map to a composition of
      `geo.city` + `category.any` + `quality.min_score`.
    - **Advanced:** render `options.available` grouped by `group`; each predicate is a control derived
      from its `params_schema` (string → text input, int → number, `list[string]` → chips), with an
      optional "not / exclude" (negate) toggle; the buyer adds conditions (top-level AND). Show
      `options.unavailable` as **greyed** rows with an honest "not available in current inventory" note
      and the coverage %. **No control without a registered predicate behind it.**
  - **Live estimate panel:** on any change (debounced ~350ms), build the composition JSON and `fetch`
    POST `/app/composer/estimate`; render `count`, the score/freshness distribution bars, and the masked
    sample cards (reuse the visual language of `ui.lead_card`; samples are `mask_preview` dicts — show
    score/category/city/`✓ Validated phone`/ODbL, NO name/number).
  - **Save as Segment:** a name input + button POSTing to `/app/composer/save` (Task 5). Keep the
    `{{ csrf }}` token for the save POST.
  - Honesty: masked samples only; ODbL on samples; "Validated" not "Verified".
  - The composition contract (build this JSON): `{"op":"AND","nodes":[{"predicate":<key>,"params":{...},
    "negate":<bool?>}, ...]}`.
- [ ] **Step 3: Nav** — in `base.html`, point the buyer "Campaigns · Preview" nav OR add a new
  "Composer" entry linking `/app/composer` (keep `/app/campaign-preview` reachable as the design mock).
- [ ] **Step 4: Verify** — `.venv/Scripts/python -c "..."` parse-check all templates; boot-import
  `import app.leadvault` OK; `rm`-free full suite passes.
- [ ] **Step 5: Commit** `feat(targeting): data-driven composer UI (guided + advanced, live estimate, masked results)`

---

### Task 5: Save / list / load Segments

**Files:** Modify `app/web/routes_buyer.py`; Create `app/web/templates/segments.html`; Modify `base.html`
(nav: "Saved searches" → point to `/app/segments`). Test: `tests/test_targeting_composer.py` (add).

**Interfaces — Produces:** `POST /app/composer/save` (csrf) → `create_segment(session, ba_id, name,
composition)`; `GET /app/segments` → list the buyer's Segments; `GET /app/composer?segment=<id>` → load a
Segment's composition into the builder (pass it to the template as `preset`).

- [ ] **Step 1: Failing test** — create a Segment via the save route (with a valid buyer session + csrf),
  assert it appears in `list_segments(session, ba_id)` with the posted composition; assert another
  buyer's `get_owned` returns None (ownership).
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** the three routes using `app.core.targeting.segments` (`create_segment`,
  `list_segments`, `get_owned`); the composer GET accepts `?segment=<id>` and, if owned, passes its
  `composition_json` to the template as `preset` for the JS to load. `segments.html` lists saved segments
  (name, created, "Open" → `/app/composer?segment=<id>`, "Delete" → `delete_segment`).
- [ ] **Step 4: Run — PASS + full suite.**
- [ ] **Step 5: Commit** `feat(targeting): save/list/load/delete Segments in the composer`

---

### Task 6: Admin backfill + grep-clean gate + consolidated INV-Q1 + review prep

**Files:** Modify `app/web/routes_admin.py` (+ `admin_overview.html` button); Test
`tests/test_composer_grepclean.py`.

- [ ] **Step 1: Admin backfill route** `POST /admin/recompute-coverage` (admin + csrf) → `recompute_coverage(session)`
  → redirect `/admin` with a count; add a button to `admin_overview.html`. (So an operator can refresh the
  rollup after a bulk change without a re-ingest.)
- [ ] **Step 2: grep-clean test** (`tests/test_composer_grepclean.py`): assert
  `grep`-pattern `quality|energy|utility|osm|overpass|campaign|provider|mca|lender` finds nothing in
  `app/core` (mirror `tests/test_quality_grepclean.py`). If a hit appears, relocate it out of core — do
  NOT weaken the test.
- [ ] **Step 3: consolidated INV-Q1** — a test asserting the full composer flow (estimate + a real
  `/app/unlock/{id}` of a composer result) holds the gate: a cold (blob-less) lead is absent from the
  estimate AND `unlock_lead` raises `LeadHeldBack` for it. (Unlock enforcement already exists; prove it
  applies to composer-surfaced leads too.)
- [ ] **Step 4: Full suite + grep + template parse.** All green.
- [ ] **Step 5: Commit** `feat(targeting): admin coverage backfill + grep-clean gate + composer INV-Q1 tests`

---

## Self-Review
**Spec coverage (v2 §6 + user reqs):** data-driven options from the coverage rollup (T1/T2), guided +
advanced split (T4), wired to the built evaluator/estimate/Segments with no mocks and honestly-greyed
unavailable predicates (T2/T4), INV-Q1 in composer paths (T3/T6), grep-clean core (T6), masking/ODbL/
suppression/compliance untouched (reuses the built spine). Live estimate reuses the built `estimate()`.

**Placeholder scan:** backend + tests carry full code; the composer JS/UI (T4) is specified by contract
(composition JSON + params_schema→control mapping + endpoints + style reference) rather than verbatim
markup — the implementer builds it against the exemplar and the parse/suite gates.

**Type consistency:** composition JSON shape `{op, nodes:[{predicate,params,negate?}]}` matches the built
`evaluate`/`matching_by_composition`/`estimate`; `predicate_options` descriptors carry `params_schema`
straight from the registered predicates; `estimate()` returns the dict the endpoint serializes.

**Deferred (correctly NOT here):** campaign-driven defaults + per-campaign quality profile (that's the
**Campaign layer**, the next increment); nested OR-groups beyond top-level AND + negate (a documented
follow-up if buyers need it); new predicate packs / Signal-Acquisition providers (each its own gated
spec). Greyed "requires licensed source" items stay greyed.

**🛑 After this plan: PAUSE for user review. Then Campaign layer, then a REAL utilities-UK demand test
with buyers. Do not build past the Campaign layer without real buyers. Payments parked.**
