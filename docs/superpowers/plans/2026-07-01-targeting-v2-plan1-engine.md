# Targeting v2 — Plan 1: Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> ⛔ **EXECUTION GATE — DO NOT START until the user posts "Stripe smoke passed."** This plan is written
> ahead of the gate. The pilot-readiness checklist must be green (its one open item is the user's Stripe
> test-mode webhook smoke on their machine) BEFORE any task here is executed. Writing the plan is allowed;
> building is not.

**Goal:** Build the server-side engine of the composable Targeting layer — a normalized lead view, a
predicate-plugin registry, a tri-state composition evaluator, a two-stage SQL+Python matcher, a Segment
model/CRUD, an estimate function, and ~7 predicates that run on today's lawful attributes.

**Architecture:** Generic engine in `app/core/targeting/` (no vertical/source/entity strings); concrete
predicates in `app/targeting/predicates/` (registered at startup like scoring profiles). Predicates read
a normalized view (dotted paths over `Lead` columns + `attributes_json`/`intent_json`/`subscores_json` +
category links), return `bool | None` (None = unknown), and the evaluator uses Kleene three-valued logic
with inclusion **iff the composition evaluates to `True`**. The matcher pushes indexed, always-known,
top-level-AND leaves into SQL, then runs the full tri-state pass in Python. Masking/suppression/opt-out/
retention/audit are untouched — reused verbatim from the marketplace spine in the estimate path.

**Tech Stack:** Python 3.11 (`.venv/Scripts/python`), FastAPI/SQLModel/SQLite, pytest. Reuses
`app/core/leadcats.py` (`lead_ids_for_categories`), `app/core/masking.py` (`mask_preview`),
`app/core/compliance.py` (`lead_opted_out`, `host_of`), `app/core/retention.py` (`is_expired`),
`app/core/marketplace.py` (`_not_suppressed`).

## Global Constraints

- Interpreter `.venv/Scripts/python`; tests `.venv/Scripts/python -m pytest`. Use Bash for git; no `cd`
  prefixes. Do NOT commit `*.db`. Before a full-suite run: `rm -f leadvault.db leadscraper.db`.
- **Secrets:** never required here; if ever needed, read from env — never a literal. (Standing rule.)
- **INV-1 (tri-state):** a predicate over an absent/empty path returns `None` (unknown), never `False`.
  Kleene logic: `not None = None`; `AND` = False if any False else None if any None else True; `OR` =
  True if any True else None if any None else False; empty `AND` = True, empty `OR` = False. A lead is
  selected **iff `evaluate(...) is True`**. Regression test REQUIRED: `NOT <signal>` excludes un-enriched
  leads.
- **INV-2 (role-email allowlist):** the role-email predicate matches `public_email` local-part ONLY
  against a fixed role-prefix allowlist, NEVER an arbitrary `firstname.lastname@`. Test REQUIRED.
- **INV-3 (masking/spine):** estimate/search over compositions still apply `mask_preview` + suppression +
  opt-out + retention exactly as `marketplace.search`. Test REQUIRED.
- **INV-4 (grep-clean core):** `grep -rinE "energy|utility|osm|overpass|shopify|gloriafood" app/core/`
  and `grep -rinE "campaign" app/core/targeting/` → empty. Concrete predicate strings live in
  `app/targeting/`. Test REQUIRED (gate).
- **INV-5 (pushdown soundness):** the two-stage matcher returns exactly the same lead set as a pure
  Python evaluation over all leads. Parity test REQUIRED.
- Composition JSON shape (v2 §5): leaf `{predicate, params, negate?}`; group `{op: "AND"|"OR", nodes:[…]}`.
  Binary groups only; per-leaf `negate`; no `NOT`-group.

---

## File Structure

```
app/core/targeting/
  __init__.py
  view.py           # lead_view(lead) + get_path(view, "a.b")  (generic)
  predicate.py      # Predicate protocol + MISSING sentinel      (generic)
  registry.py       # register/get/all_keys/available            (generic)
  composition.py    # evaluate() tri-state + matching_by_composition() two-stage (generic)
  segments.py       # Segment CRUD, ownership-guarded             (generic)
  estimate.py       # estimate() count + distributions + masked samples (generic; reuses spine)
app/core/db.py      # + Segment model (lv_segment)
app/targeting/
  __init__.py
  predicates/
    __init__.py
    geo.py            # geo.country, geo.region, geo.city   (+ sql_pushdown)
    quality.py        # quality.min_score, freshness.verified_within, source.type (+ sql_pushdown)
    category.py       # category.any                        (+ sql_pushdown via link table)
    contactability.py # contactability.has_phone, .has_role_email (INV-2), .has_business_contact
    webpresence.py    # web.has_signal (tri-state), web.is_enriched
  runtime.py          # register_targeting_runtime()
tests/
  test_targeting_view.py test_targeting_registry.py test_targeting_eval.py
  test_targeting_segments.py test_targeting_predicates.py test_targeting_matcher.py
  test_targeting_estimate.py test_targeting_grepclean.py
```

---

### Task 1: Normalized lead view

**Files:**
- Create: `app/core/targeting/__init__.py` (empty), `app/core/targeting/view.py`
- Test: `tests/test_targeting_view.py`

**Interfaces:**
- Produces: `lead_view(lead) -> dict` (canonical projection); `get_path(view: dict, path: str)` returns
  the value at a dotted path or the `MISSING` sentinel (from `predicate.py`, Task 2 — for Task 1 define a
  local `_MISSING = object()` and export `MISSING = _MISSING`; Task 2 imports it).

- [ ] **Step 1: Write the failing test**
```python
import json
from app.core.db import Lead
from app.core.targeting.view import lead_view, get_path, MISSING


def test_lead_view_projects_columns_and_json_blobs():
    lead = Lead(business_name="X", city="London", country="GB", score_total=77,
                phone="123", public_email="info@x.com", website_url="https://x.com",
                category_keys_json=json.dumps(["cafe", "bakery"]),
                attributes_json=json.dumps({"detected_platform": "p", "open_7_days": True}),
                intent_json=json.dumps({"ssl": True, "online_ordering_detected": False}),
                subscores_json=json.dumps({"confidence": 90}))
    v = lead_view(lead)
    assert v["city"] == "London" and v["country"] == "GB" and v["score_total"] == 77
    assert v["category_keys"] == ["cafe", "bakery"]
    assert get_path(v, "attributes.detected_platform") == "p"
    assert get_path(v, "intent.ssl") is True
    assert get_path(v, "subscores.confidence") == 90
    # absent path -> MISSING (never a guessed False)
    assert get_path(v, "intent.does_not_exist") is MISSING
    assert get_path(v, "attributes.nope") is MISSING
```

- [ ] **Step 2: Run it — FAIL** (`ModuleNotFoundError`).
Run: `.venv/Scripts/python -m pytest tests/test_targeting_view.py -q`

- [ ] **Step 3: Implement `app/core/targeting/view.py`**
```python
from __future__ import annotations

import json

MISSING = object()  # sentinel: path absent (distinct from a stored None/False)


def _load(blob: str) -> dict:
    try:
        return json.loads(blob or "{}") or {}
    except (ValueError, TypeError):
        return {}


def lead_view(lead) -> dict:
    return {
        "id": lead.id, "business_name": lead.business_name,
        "category_keys": (_load(lead.category_keys_json) if isinstance(lead.category_keys_json, str)
                          else lead.category_keys_json) if False else json.loads(lead.category_keys_json or "[]"),
        "city": lead.city, "region": lead.region, "country": lead.country,
        "postal_code": lead.postal_code, "latitude": lead.latitude, "longitude": lead.longitude,
        "phone": lead.phone, "public_email": lead.public_email, "website_url": lead.website_url,
        "opening_hours": getattr(lead, "opening_hours", ""),
        "score_total": lead.score_total, "subscores": _load(lead.subscores_json),
        "attributes": _load(lead.attributes_json), "intent": _load(lead.intent_json),
        "source_key": lead.source_key, "source_license": lead.source_license,
        "scoring_profile_key": lead.scoring_profile_key,
        "date_discovered": lead.date_discovered, "date_last_verified": lead.date_last_verified,
        "retention_expiry": lead.retention_expiry, "times_sold": lead.times_sold,
    }


def get_path(view: dict, path: str):
    cur = view
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return MISSING
    return cur
```
(Simplify the `category_keys` line to `json.loads(lead.category_keys_json or "[]")`; the ternary above is
noise — the implementer should write just that.)

- [ ] **Step 4: Run — PASS.** `.venv/Scripts/python -m pytest tests/test_targeting_view.py -q`
- [ ] **Step 5: Commit**
```bash
git add app/core/targeting/__init__.py app/core/targeting/view.py tests/test_targeting_view.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(targeting): normalized lead view + dotted-path accessor (MISSING sentinel)"
```

---

### Task 2: Predicate protocol + registry

**Files:**
- Create: `app/core/targeting/predicate.py`, `app/core/targeting/registry.py`
- Test: `tests/test_targeting_registry.py`

**Interfaces:**
- Produces: `Predicate` Protocol `{key, group, label, reads: list[str], params_schema: dict,
  matches(view, params) -> bool | None}` (optional `sql_pushdown(params)` used by Task 6);
  `register(p)`, `get(key) -> Predicate`, `all_keys() -> list[str]`,
  `available(populated_paths: set[str]) -> list[Predicate]` (predicates whose `reads ⊆ populated_paths`);
  `clear()` (test hygiene).

- [ ] **Step 1: Write the failing test**
```python
import pytest
from app.core.targeting import registry


class _Fake:
    key = "x.demo"; group = "demo"; label = "Demo"; reads = ["intent.ssl"]; params_schema = {}
    def matches(self, view, params): return True


def test_register_get_all_and_available():
    registry.clear()
    p = _Fake()
    registry.register(p)
    assert registry.get("x.demo") is p
    assert registry.all_keys() == ["x.demo"]
    assert registry.available({"intent.ssl", "city"}) == [p]      # reads satisfied
    assert registry.available({"city"}) == []                     # reads not populated
    with pytest.raises(KeyError):
        registry.get("nope")
```

- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement**
`app/core/targeting/predicate.py`:
```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.targeting.view import MISSING  # re-export for predicate authors

__all__ = ["Predicate", "MISSING"]


@runtime_checkable
class Predicate(Protocol):
    key: str
    group: str
    label: str
    reads: list[str]
    params_schema: dict
    def matches(self, view: dict, params: dict) -> "bool | None": ...
    # optional: def sql_pushdown(self, params: dict): -> SQLAlchemy clause or None
```
`app/core/targeting/registry.py`:
```python
from __future__ import annotations

_PREDS: dict = {}


def register(predicate) -> None:
    _PREDS[predicate.key] = predicate


def get(key: str):
    if key not in _PREDS:
        raise KeyError(f"no predicate '{key}'")
    return _PREDS[key]


def all_keys() -> list[str]:
    return sorted(_PREDS.keys())


def available(populated_paths: set) -> list:
    return [p for p in _PREDS.values() if set(p.reads) <= set(populated_paths)]


def clear() -> None:
    _PREDS.clear()
```

- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit**
```bash
git add app/core/targeting/predicate.py app/core/targeting/registry.py tests/test_targeting_registry.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(targeting): predicate protocol + registry (data-driven available())"
```

---

### Task 3: Tri-state composition evaluator (INV-1)

**Files:**
- Create: `app/core/targeting/composition.py` (evaluate + selects only; matcher added in Task 6)
- Test: `tests/test_targeting_eval.py`

**Interfaces:**
- Consumes: `registry.get`.
- Produces: `kleene_and(vals)`, `kleene_or(vals)`, `kleene_not(v)`; `evaluate(view, node) -> bool | None`;
  `selects(view, composition) -> bool` (`evaluate(...) is True`).

- [ ] **Step 1: Write the failing test (the INV-1 truth table + "NOT excludes un-enriched")**
```python
from app.core.targeting import registry
from app.core.targeting.composition import (evaluate, selects,
                                            kleene_and, kleene_or, kleene_not)
from app.core.targeting.view import get_path, MISSING


class _Signal:
    # returns True/False from view["intent"][name], or None when the path is absent (un-enriched)
    def __init__(self, key, name):
        self.key = key; self.group = "web"; self.label = key
        self.reads = [f"intent.{name}"]; self.params_schema = {}; self._name = name
    def matches(self, view, params):
        val = get_path(view, f"intent.{self._name}")
        return None if val is MISSING else bool(val)


def _setup():
    registry.clear()
    registry.register(_Signal("web.ecom", "ecommerce_detected"))


def test_kleene_truth_tables():
    assert kleene_not(True) is False and kleene_not(False) is True and kleene_not(None) is None
    assert kleene_and([True, True]) is True
    assert kleene_and([True, False]) is False
    assert kleene_and([True, None]) is None
    assert kleene_and([False, None]) is False
    assert kleene_and([]) is True                    # empty AND -> True
    assert kleene_or([False, None]) is None
    assert kleene_or([True, None]) is True
    assert kleene_or([False, False]) is False
    assert kleene_or([]) is False                    # empty OR -> False


def test_include_iff_true_and_empty_composition():
    _setup()
    assert selects({}, {"op": "AND", "nodes": []}) is True      # empty composition matches all


def test_not_signal_excludes_unenriched_leads():
    _setup()
    enriched_true = {"intent": {"ecommerce_detected": True}}
    enriched_false = {"intent": {"ecommerce_detected": False}}
    unenriched = {"intent": {}}                                  # signal ABSENT
    comp = {"op": "AND", "nodes": [{"predicate": "web.ecom", "negate": True}]}
    # NOT ecommerce -> only leads KNOWN not to have it; never un-enriched
    assert selects(enriched_false, comp) is True
    assert selects(enriched_true, comp) is False
    assert selects(unenriched, comp) is False                    # <-- the invariant
    # positive filter likewise excludes un-enriched
    pos = {"op": "AND", "nodes": [{"predicate": "web.ecom"}]}
    assert selects(unenriched, pos) is False
    assert selects(enriched_true, pos) is True
```

- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement `app/core/targeting/composition.py`**
```python
from __future__ import annotations

from app.core.targeting import registry


def kleene_not(v):
    return None if v is None else (not v)


def kleene_and(vals):
    if any(v is False for v in vals):
        return False
    if any(v is None for v in vals):
        return None
    return True


def kleene_or(vals):
    if any(v is True for v in vals):
        return True
    if any(v is None for v in vals):
        return None
    return False


def evaluate(view: dict, node: dict):
    if "op" in node:
        vals = [evaluate(view, child) for child in node.get("nodes", [])]
        return kleene_and(vals) if node["op"] == "AND" else kleene_or(vals)
    pred = registry.get(node["predicate"])
    v = pred.matches(view, node.get("params", {}))
    if node.get("negate"):
        v = kleene_not(v)
    return v


def selects(view: dict, composition: dict) -> bool:
    return evaluate(view, composition) is True
```

- [ ] **Step 4: Run — PASS.** `.venv/Scripts/python -m pytest tests/test_targeting_eval.py -q`
- [ ] **Step 5: Commit**
```bash
git add app/core/targeting/composition.py tests/test_targeting_eval.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(targeting): tri-state Kleene composition evaluator (INV-1; NOT excludes un-enriched)"
```

---

### Task 4: Segment model + CRUD

**Files:**
- Modify: `app/core/db.py` (+ `Segment`)
- Create: `app/core/targeting/segments.py`
- Test: `tests/test_targeting_segments.py`

**Interfaces:**
- Produces: `Segment` (`lv_segment`: id, buyer_account_id [indexed], name, composition_json,
  source_campaign_key, created_at, updated_at); `create_segment(session, buyer_account_id, name,
  composition: dict) -> Segment`; `list_segments(session, buyer_account_id) -> list[Segment]`;
  `get_owned(session, segment_id, buyer_account_id) -> Segment | None`;
  `update_segment(session, segment_id, buyer_account_id, *, name=None, composition=None) -> Segment`.

- [ ] **Step 1: Write the failing test**
```python
import json
from sqlmodel import Session
from app.core.db import init_db, Segment
from app.core.targeting.segments import (create_segment, list_segments, get_owned, update_segment)


def test_segment_crud_is_owner_scoped():
    e = init_db("sqlite://")
    with Session(e) as s:
        comp = {"op": "AND", "nodes": [{"predicate": "geo.country", "params": {"value": "GB"}}]}
        seg = create_segment(s, 1, "UK cafes", comp)
        assert seg.id and json.loads(seg.composition_json) == comp
        assert [x.id for x in list_segments(s, 1)] == [seg.id]
        assert list_segments(s, 2) == []                       # buyer-scoped
        assert get_owned(s, seg.id, 1).name == "UK cafes"
        assert get_owned(s, seg.id, 2) is None                 # ownership guard
        up = update_segment(s, seg.id, 1, name="renamed")
        assert up.name == "renamed" and up.updated_at is not None
        assert update_segment(s, seg.id, 2, name="hijack") is None  # cannot update others'
```

- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3a: Add `Segment` to `app/core/db.py`** (near the other models; `_now` exists):
```python
class Segment(SQLModel, table=True):
    __tablename__ = "lv_segment"
    id: int | None = Field(default=None, primary_key=True)
    buyer_account_id: int = Field(default=0, index=True)
    name: str = ""
    composition_json: str = "{}"
    source_campaign_key: str = ""   # optional provenance (Campaign layer)
    created_at: str = Field(default_factory=_now)
    updated_at: str | None = None
```
- [ ] **Step 3b: Implement `app/core/targeting/segments.py`**
```python
from __future__ import annotations

import json

from sqlmodel import Session, select

from app.core.db import Segment, _now


def create_segment(session: Session, buyer_account_id: int, name: str,
                   composition: dict, *, source_campaign_key: str = "") -> Segment:
    seg = Segment(buyer_account_id=buyer_account_id, name=name,
                  composition_json=json.dumps(composition),
                  source_campaign_key=source_campaign_key)
    session.add(seg); session.commit(); session.refresh(seg)
    return seg


def list_segments(session: Session, buyer_account_id: int) -> list:
    return session.exec(select(Segment).where(
        Segment.buyer_account_id == buyer_account_id).order_by(Segment.id.desc())).all()


def get_owned(session: Session, segment_id: int, buyer_account_id: int):
    seg = session.get(Segment, segment_id)
    if seg is None or seg.buyer_account_id != buyer_account_id:
        return None
    return seg


def update_segment(session: Session, segment_id: int, buyer_account_id: int, *,
                   name: str | None = None, composition: dict | None = None):
    seg = get_owned(session, segment_id, buyer_account_id)
    if seg is None:
        return None
    if name is not None:
        seg.name = name
    if composition is not None:
        seg.composition_json = json.dumps(composition)
    seg.updated_at = _now()
    session.add(seg); session.commit(); session.refresh(seg)
    return seg
```

- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit**
```bash
git add app/core/db.py app/core/targeting/segments.py tests/test_targeting_segments.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(targeting): Segment model (lv_segment) + owner-scoped CRUD"
```

---

### Task 5: The NOW predicates + runtime registration (INV-2)

**Files:**
- Create: `app/targeting/__init__.py`, `app/targeting/predicates/__init__.py`,
  `app/targeting/predicates/{geo,quality,category,contactability,webpresence}.py`,
  `app/targeting/runtime.py`
- Test: `tests/test_targeting_predicates.py`

**Interfaces:**
- Consumes: `registry.register`, `get_path`/`MISSING`, `lead_ids_for_categories`.
- Produces predicates (keys): `geo.country`, `geo.region`, `geo.city`, `quality.min_score`,
  `freshness.verified_within`, `source.type`, `category.any`, `contactability.has_phone`,
  `contactability.has_role_email`, `contactability.has_business_contact`, `web.has_signal`,
  `web.is_enriched`; and `register_targeting_runtime()` that registers them all. Predicates for indexed
  columns also expose `sql_pushdown(params)` (used by Task 6). Category/geo/quality/freshness/source
  predicates read populated column paths; `contactability.*` read `phone`/`public_email`;
  `web.has_signal` reads `intent.<param>`; `web.is_enriched` reads `intent.last_scanned`.

- [ ] **Step 1: Write the failing test (behavior + INV-2 + tri-state)**
```python
from app.core.targeting import registry
from app.core.targeting.runtime import register_targeting_runtime
from app.core.targeting.view import lead_view
from app.core.db import Lead
import json


def _view(**kw):
    base = dict(city="London", country="GB", phone="", public_email="", score_total=50,
                attributes_json="{}", intent_json="{}", subscores_json="{}",
                category_keys_json="[]")
    base.update(kw)
    return lead_view(Lead(**base))


def test_predicates_registered():
    registry.clear(); register_targeting_runtime()
    for k in ["geo.country", "geo.city", "quality.min_score", "freshness.verified_within",
              "category.any", "contactability.has_business_contact", "web.has_signal",
              "web.is_enriched", "contactability.has_role_email"]:
        assert registry.get(k)


def test_geo_and_score_predicates():
    registry.clear(); register_targeting_runtime()
    v = _view(country="GB", city="London", score_total=80)
    assert registry.get("geo.country").matches(v, {"value": "GB"}) is True
    assert registry.get("geo.country").matches(v, {"value": "FR"}) is False
    assert registry.get("quality.min_score").matches(v, {"min": 70}) is True
    assert registry.get("quality.min_score").matches(v, {"min": 90}) is False


def test_role_email_allowlist_invariant():   # INV-2
    registry.clear(); register_targeting_runtime()
    p = registry.get("contactability.has_role_email")
    assert p.matches(_view(public_email="info@acme.com"), {}) is True
    assert p.matches(_view(public_email="sales@acme.com"), {}) is True
    assert p.matches(_view(public_email="john.smith@acme.com"), {}) is False   # personal -> NOT role
    assert p.matches(_view(public_email=""), {}) is None                        # absent -> unknown


def test_web_signal_is_tristate():
    registry.clear(); register_targeting_runtime()
    p = registry.get("web.has_signal")
    assert p.matches(_view(intent_json=json.dumps({"ecommerce_detected": True})),
                     {"signal": "ecommerce_detected"}) is True
    assert p.matches(_view(intent_json=json.dumps({"ecommerce_detected": False})),
                     {"signal": "ecommerce_detected"}) is False
    assert p.matches(_view(intent_json="{}"), {"signal": "ecommerce_detected"}) is None  # un-enriched
```

- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement the predicate modules.** Each predicate is a small class; `matches` returns
  `bool | None` using `get_path`/`MISSING`. Indexed ones also define `sql_pushdown(params)` returning a
  SQLAlchemy clause on `Lead` (imported from `app.core.db`).

`app/targeting/predicates/geo.py`:
```python
from __future__ import annotations
from app.core.db import Lead
from app.core.targeting.view import get_path, MISSING


class _GeoEq:
    def __init__(self, key, path, column, label):
        self.key = key; self.group = "geographic"; self.label = label
        self.reads = [path]; self.params_schema = {"value": "string"}
        self._path = path; self._col = column
    def matches(self, view, params):
        val = get_path(view, self._path)
        if val is MISSING or val in (None, ""):
            return None
        want = (params.get("value") or "")
        return want.lower() in str(val).lower() if want else None
    def sql_pushdown(self, params):
        want = (params.get("value") or "")
        return self._col.ilike(f"%{want}%") if want else None


GEO_COUNTRY = _GeoEq("geo.country", "country", Lead.country, "Country")
GEO_REGION = _GeoEq("geo.region", "region", Lead.region, "Region")
GEO_CITY = _GeoEq("geo.city", "city", Lead.city, "City")
```
`app/targeting/predicates/quality.py`:
```python
from __future__ import annotations
from datetime import datetime, timezone
from app.core.db import Lead
from app.core.targeting.view import get_path, MISSING


class _MinScore:
    key = "quality.min_score"; group = "quality"; label = "Minimum score"
    reads = ["score_total"]; params_schema = {"min": "int"}
    def matches(self, view, params):
        return int(view.get("score_total", 0)) >= int(params.get("min", 0))
    def sql_pushdown(self, params):
        return Lead.score_total >= int(params.get("min", 0))


class _VerifiedWithin:
    key = "freshness.verified_within"; group = "freshness"; label = "Verified within N days"
    reads = ["date_last_verified"]; params_schema = {"days": "int"}
    def matches(self, view, params):
        iso = get_path(view, "date_last_verified")
        if iso is MISSING or not iso:
            return None
        try:
            dt = datetime.fromisoformat(iso)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
        return days <= int(params.get("days", 0))


class _SourceType:
    key = "source.type"; group = "verification"; label = "Source"
    reads = ["source_key"]; params_schema = {"value": "string"}
    def matches(self, view, params):
        val = get_path(view, "source_key")
        if val is MISSING or not val:
            return None
        return str(val) == params.get("value")
    def sql_pushdown(self, params):
        return Lead.source_key == params.get("value")


MIN_SCORE = _MinScore(); VERIFIED_WITHIN = _VerifiedWithin(); SOURCE_TYPE = _SourceType()
```
`app/targeting/predicates/category.py`:
```python
from __future__ import annotations
from app.core.db import Lead, LeadCategoryLink
from app.core.leadcats import lead_ids_for_categories


class _CategoryAny:
    key = "category.any"; group = "firmographic"; label = "Category is any of"
    reads = ["category_keys"]; params_schema = {"in": "list[string]"}
    def matches(self, view, params):
        want = set(params.get("in") or [])
        if not want:
            return None
        return bool(set(view.get("category_keys") or []) & want)
    # sql_pushdown needs the session -> handled specially in Task 6 via lead_ids_for_categories


CATEGORY_ANY = _CategoryAny()
```
`app/targeting/predicates/contactability.py`:
```python
from __future__ import annotations
from app.core.targeting.view import get_path, MISSING

ROLE_PREFIXES = {"info", "sales", "support", "hello", "contact", "enquiries",
                 "enquiry", "admin", "office", "accounts", "bookings", "help"}


def _local(email: str) -> str:
    return (email or "").split("@", 1)[0].strip().lower()


class _HasPhone:
    key = "contactability.has_phone"; group = "contactability"; label = "Has phone"
    reads = ["phone"]; params_schema = {}
    def matches(self, view, params):
        val = get_path(view, "phone")
        if val is MISSING:
            return None
        return bool(val)


class _HasRoleEmail:   # INV-2: business-role local-part allowlist ONLY
    key = "contactability.has_role_email"; group = "contactability"; label = "Has role-based email"
    reads = ["public_email"]; params_schema = {}
    def matches(self, view, params):
        val = get_path(view, "public_email")
        if val is MISSING or not val:
            return None
        return _local(val) in ROLE_PREFIXES


class _HasBusinessContact:
    key = "contactability.has_business_contact"; group = "contactability"; label = "Has business contact"
    reads = ["phone", "public_email"]; params_schema = {}
    def matches(self, view, params):
        phone = get_path(view, "phone"); email = get_path(view, "public_email")
        has_phone = bool(phone) if phone is not MISSING else False
        has_role = (_local(email) in ROLE_PREFIXES) if (email is not MISSING and email) else False
        if has_phone or has_role:
            return True
        # neither present-and-usable: if both fields absent -> unknown; else known-False
        if phone is MISSING and (email is MISSING or not email):
            return None
        return False


HAS_PHONE = _HasPhone(); HAS_ROLE_EMAIL = _HasRoleEmail(); HAS_BUSINESS_CONTACT = _HasBusinessContact()
```
`app/targeting/predicates/webpresence.py`:
```python
from __future__ import annotations
from app.core.targeting.view import get_path, MISSING


class _HasSignal:   # tri-state exerciser
    key = "web.has_signal"; group = "web_presence"; label = "Web signal present"
    reads = ["intent"]; params_schema = {"signal": "string"}
    def matches(self, view, params):
        val = get_path(view, f"intent.{params.get('signal', '')}")
        return None if val is MISSING else bool(val)


class _IsEnriched:   # meta: never unknown
    key = "web.is_enriched"; group = "web_presence"; label = "Web-enriched"
    reads = ["intent.last_scanned"]; params_schema = {}
    def matches(self, view, params):
        return get_path(view, "intent.last_scanned") is not MISSING


HAS_SIGNAL = _HasSignal(); IS_ENRICHED = _IsEnriched()
```
`app/targeting/runtime.py`:
```python
from __future__ import annotations
from app.core.targeting import registry
from app.targeting.predicates import geo, quality, category, contactability, webpresence


def register_targeting_runtime() -> None:
    for p in (geo.GEO_COUNTRY, geo.GEO_REGION, geo.GEO_CITY,
              quality.MIN_SCORE, quality.VERIFIED_WITHIN, quality.SOURCE_TYPE,
              category.CATEGORY_ANY,
              contactability.HAS_PHONE, contactability.HAS_ROLE_EMAIL,
              contactability.HAS_BUSINESS_CONTACT,
              webpresence.HAS_SIGNAL, webpresence.IS_ENRICHED):
        registry.register(p)
```
(Add empty `app/targeting/__init__.py` and `app/targeting/predicates/__init__.py`.)

- [ ] **Step 4: Run — PASS.** `.venv/Scripts/python -m pytest tests/test_targeting_predicates.py -q`
- [ ] **Step 5: Commit**
```bash
git add app/targeting tests/test_targeting_predicates.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(targeting): NOW predicate pack + runtime registration (INV-2 role-email allowlist)"
```

---

### Task 6: Two-stage matcher (INV-5)

**Files:**
- Modify: `app/core/targeting/composition.py` (+ `matching_by_composition`)
- Test: `tests/test_targeting_matcher.py`

**Interfaces:**
- Consumes: `evaluate`/`selects`, `lead_view`, `registry`, `Lead`, `lead_ids_for_categories`.
- Produces: `matching_by_composition(session, composition, *, exclude_lead_ids=frozenset()) -> list[Lead]`.
  Two stages: (1) SQL pre-narrow — for a **top-level AND** composition, collect `sql_pushdown(params)`
  clauses from **non-negated leaf** children whose predicate provides one (and handle `category.any`
  specially via `lead_ids_for_categories`); build `select(Lead).where(*clauses)`. Otherwise, or for any
  non-pushable node, the candidate set is all leads. (2) Python tri-state pass: keep a candidate iff
  `selects(lead_view(lead), composition)` and `lead.id not in exclude_lead_ids`.

- [ ] **Step 1: Write the failing test (correctness + INV-5 parity)**
```python
import json
from sqlmodel import Session, select
from app.core.db import init_db, Lead, _now
from app.core.leadcats import sync_lead_categories
from app.core.targeting import registry
from app.core.targeting.runtime import register_targeting_runtime
from app.core.targeting.composition import matching_by_composition, selects
from app.core.targeting.view import lead_view


def _seed(s):
    a = Lead(business_name="A", country="GB", city="London", score_total=90, phone="1",
             category_keys_json=json.dumps(["cafe"]), date_last_verified=_now(),
             intent_json=json.dumps({"ecommerce_detected": True}))
    b = Lead(business_name="B", country="GB", city="Leeds", score_total=40, phone="",
             category_keys_json=json.dumps(["gym"]), date_last_verified=_now(),
             intent_json="{}")  # un-enriched
    c = Lead(business_name="C", country="FR", city="Paris", score_total=95, phone="3",
             category_keys_json=json.dumps(["cafe"]), date_last_verified=_now(),
             intent_json=json.dumps({"ecommerce_detected": False}))
    for x in (a, b, c):
        s.add(x)
    s.commit()
    for x in (a, b, c):
        s.refresh(x); sync_lead_categories(s, x)
    return a, b, c


def _pure_python(s, comp):
    return sorted(l.business_name for l in s.exec(select(Lead)).all()
                  if selects(lead_view(l), comp))


def test_matcher_correct_and_parity():
    e = init_db("sqlite://")
    registry.clear(); register_targeting_runtime()
    with Session(e) as s:
        _seed(s)
        comp = {"op": "AND", "nodes": [
            {"predicate": "geo.country", "params": {"value": "GB"}},
            {"predicate": "quality.min_score", "params": {"min": 50}},
            {"predicate": "category.any", "params": {"in": ["cafe"]}}]}
        got = sorted(l.business_name for l in matching_by_composition(s, comp))
        assert got == ["A"]                       # GB + score>=50 + cafe
        assert got == _pure_python(s, comp)       # INV-5 parity
        # NOT ecommerce excludes the un-enriched B (INV-1 through the matcher)
        notc = {"op": "AND", "nodes": [
            {"predicate": "geo.country", "params": {"value": "GB"}},
            {"predicate": "web.has_signal", "params": {"signal": "ecommerce_detected"},
             "negate": True}]}
        assert sorted(l.business_name for l in matching_by_composition(s, notc)) == []
        assert sorted(l.business_name for l in matching_by_composition(s, notc)) == _pure_python(s, notc)
```

- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Add `matching_by_composition` to `app/core/targeting/composition.py`**
```python
from sqlmodel import select
from app.core.db import Lead
from app.core.leadcats import lead_ids_for_categories
from app.core.targeting.view import lead_view


def _pushdown_clauses(session, composition):
    """Sound, conservative pushdown: only for a top-level AND, only non-negated leaves whose
    predicate exposes sql_pushdown (or category.any via the link table). Returns a list of
    SQLAlchemy clauses, or None to signal 'no safe pushdown -> scan all'."""
    if composition.get("op") != "AND":
        return None
    clauses = []
    for node in composition.get("nodes", []):
        if "op" in node or node.get("negate"):
            continue  # nested groups / negation are not pushed (handled in Python)
        pred = registry.get(node["predicate"])
        params = node.get("params", {})
        if pred.key == "category.any":
            ids = lead_ids_for_categories(session, params.get("in") or [])
            clauses.append(Lead.id.in_(ids) if ids else Lead.id.in_([-1]))
            continue
        fn = getattr(pred, "sql_pushdown", None)
        if fn is not None:
            clause = fn(params)
            if clause is not None:
                clauses.append(clause)
    return clauses


def matching_by_composition(session, composition, *, exclude_lead_ids=frozenset()):
    clauses = _pushdown_clauses(session, composition)
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
(Note: pushdown is an OPTIMIZATION — stage 2 `selects()` is authoritative, so an over-broad candidate
set is still correct. The parity test proves stage 1 never drops a matching lead.)

- [ ] **Step 4: Run — PASS.** `.venv/Scripts/python -m pytest tests/test_targeting_matcher.py -q`
- [ ] **Step 5: Commit**
```bash
git add app/core/targeting/composition.py tests/test_targeting_matcher.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(targeting): two-stage SQL+Python matcher (INV-5 pushdown parity)"
```

---

### Task 7: Estimate (INV-3 masking + compliance spine)

**Files:**
- Create: `app/core/targeting/estimate.py`
- Test: `tests/test_targeting_estimate.py`

**Interfaces:**
- Consumes: `matching_by_composition`, `mask_preview` (`app/core/masking.py`), `is_expired`
  (`app/core/retention.py`), `lead_opted_out` (`app/core/compliance.py`), `_not_suppressed`
  (`app/core/marketplace.py`).
- Produces: `estimate(session, buyer_account_id, composition, *, sample=8) -> dict` with keys `count`,
  `score_distribution` (bands `[0-49,50-69,70-84,85-100]`), `freshness_distribution` (bands
  `[<=7,<=30,<=90,older]` days), `samples` (≤`sample` **masked** previews). Applies the SAME
  post-selection spine as `marketplace.search`: skip expired, opted-out, suppressed. (Debounce/caching is
  a Plan-2 UI concern; this is the pure function.)

- [ ] **Step 1: Write the failing test**
```python
import json
from sqlmodel import Session
from app.core.db import init_db, Lead, OptOutRequest, _now
from app.core.leadcats import sync_lead_categories
from app.core.targeting import registry
from app.core.targeting.runtime import register_targeting_runtime
from app.core.targeting.estimate import estimate


def test_estimate_masks_and_respects_compliance():
    e = init_db("sqlite://")
    registry.clear(); register_targeting_runtime()
    with Session(e) as s:
        keep = Lead(business_name="Keep", country="GB", city="London", score_total=90, phone="1",
                    public_email="info@keep.com", website_url="https://keep.com",
                    category_keys_json=json.dumps(["cafe"]), date_last_verified=_now())
        gone = Lead(business_name="Gone", country="GB", city="London", score_total=88, phone="2",
                    website_url="https://gone.com",
                    category_keys_json=json.dumps(["cafe"]), date_last_verified=_now())
        s.add(keep); s.add(gone); s.commit()
        for x in (keep, gone):
            s.refresh(x); sync_lead_categories(s, x)
        s.add(OptOutRequest(kind="domain", value="gone.com", applied=True)); s.commit()
        comp = {"op": "AND", "nodes": [{"predicate": "geo.country", "params": {"value": "GB"}}]}
        est = estimate(s, 1, comp)
        assert est["count"] == 1                              # opted-out 'Gone' excluded
        blob = json.dumps(est["samples"])
        assert "Keep" not in blob and "info@keep.com" not in blob and "keep.com" not in blob  # masked
        assert sum(est["score_distribution"].values()) == 1
        assert sum(est["freshness_distribution"].values()) == 1
```

- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement `app/core/targeting/estimate.py`**
```python
from __future__ import annotations

from datetime import datetime, timezone

from app.core.masking import mask_preview
from app.core.retention import is_expired
from app.core.compliance import lead_opted_out
from app.core.marketplace import _not_suppressed
from app.core.targeting.composition import matching_by_composition


def _days(iso):
    if not iso:
        return 1e9
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return 1e9
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0


def _score_band(v):
    return "0-49" if v < 50 else "50-69" if v < 70 else "70-84" if v < 85 else "85-100"


def _fresh_band(d):
    return "<=7" if d <= 7 else "<=30" if d <= 30 else "<=90" if d <= 90 else "older"


def estimate(session, buyer_account_id, composition, *, sample: int = 8) -> dict:
    leads = matching_by_composition(session, composition)
    visible = [l for l in leads
               if not is_expired(l)
               and not lead_opted_out(session, l)
               and _not_suppressed(session, buyer_account_id, l)]
    sd = {"0-49": 0, "50-69": 0, "70-84": 0, "85-100": 0}
    fd = {"<=7": 0, "<=30": 0, "<=90": 0, "older": 0}
    for l in visible:
        sd[_score_band(l.score_total)] += 1
        fd[_fresh_band(_days(l.date_last_verified))] += 1
    return {"count": len(visible), "score_distribution": sd,
            "freshness_distribution": fd,
            "samples": [mask_preview(l) for l in visible[:sample]]}
```
(If `_not_suppressed` is not importable/named differently in `marketplace.py`, the implementer should
use the same suppression check `marketplace.search` uses — read that file and match it exactly.)

- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit**
```bash
git add app/core/targeting/estimate.py tests/test_targeting_estimate.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(targeting): estimate (masked samples + score/freshness distributions; INV-3 spine reused)"
```

---

### Task 8: Grep-clean gate + startup registration (INV-4)

**Files:**
- Modify: `app/leadvault.py` (call `register_targeting_runtime()` at startup)
- Test: `tests/test_targeting_grepclean.py`

**Interfaces:**
- Consumes: `register_targeting_runtime`.
- Produces: predicates registered on app import; a grep-clean assertion test.

- [ ] **Step 1: Write the failing test**
```python
import pathlib
import re


def test_core_targeting_is_grep_clean():
    root = pathlib.Path("app/core")
    pat = re.compile(r"energy|utility|osm|overpass|shopify|gloriafood|campaign", re.I)
    hits = []
    for p in root.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if pat.search(line):
                hits.append(f"{p}:{i}: {line.strip()}")
    assert hits == [], "forbidden strings leaked into app/core:\n" + "\n".join(hits)


def test_predicates_registered_on_app_import():
    import app.leadvault  # noqa: F401  (import triggers registration)
    from app.core.targeting import registry
    assert "geo.country" in registry.all_keys()
    assert "web.has_signal" in registry.all_keys()
```

- [ ] **Step 2: Run — FAIL** (registration not wired; possibly grep hits if any slipped).
- [ ] **Step 3: Wire startup registration in `app/leadvault.py`** — after the router includes, add:
```python
from app.targeting.runtime import register_targeting_runtime
register_targeting_runtime()
```
(If `test_core_targeting_is_grep_clean` finds a real leak, move the offending string out of `app/core`
into `app/targeting/` — do NOT weaken the test.)

- [ ] **Step 4: Run — PASS.** Then full suite:
`rm -f leadvault.db leadscraper.db && .venv/Scripts/python -m pytest -q` — all pass, zero collection errors.

- [ ] **Step 5: Commit**
```bash
git add app/leadvault.py tests/test_targeting_grepclean.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(targeting): register predicates at startup + grep-clean core gate (INV-4)"
```

---

## Self-Review

**Spec coverage (Targeting v2 §14 Plan 1):**
- normalized view → Task 1 ✓ · predicate interface + registry → Task 2 ✓ · tri-state evaluator (INV-1,
  incl. "NOT excludes un-enriched" + truth table) → Task 3 ✓ · Segment model/CRUD → Task 4 ✓ · ~6 NOW
  predicates (geo/quality/freshness/source/category/contactability/web) → Task 5 ✓ · two-stage evaluator
  (INV-5 parity) → Task 6 ✓ · estimate (INV-3 masking + spine) → Task 7 ✓ · grep-clean (INV-4) +
  startup registration → Task 8 ✓.
- INV-1..INV-5 each have an explicit test (Tasks 3, 5, 7, 6, 6). INV-2 role-email allowlist → Task 5.
- Deferred to Plan 2 (per v2 §14): the composer UI, the `lv_attribute_coverage` rollup + provider
  `provides` declarations + populated-% display, and estimate debounce/caching. Not in this plan by
  design.

**Placeholder scan:** none — every step has runnable code + commands. (Task 1 flags one noisy line to
simplify; the intended one-liner is stated.)

**Type consistency:** `matches(view, params) -> bool | None` used uniformly; `evaluate`/`selects`/
`matching_by_composition` signatures match across Tasks 3/6/7; `MISSING` sentinel defined in Task 1,
re-exported in Task 2, used in Task 5; predicate `key` strings referenced in tests match the keys
registered in Task 5; `sql_pushdown` optional method consumed via `getattr` in Task 6 exactly as defined
in Task 5.

**Note for the executor:** confirm `_not_suppressed` (or the equivalent suppression check) in
`app/core/marketplace.py` before Task 7 — match `marketplace.search`'s exact call. If it differs, adjust
the import in `estimate.py` and the test accordingly (behavior unchanged: opted-out/suppressed/expired
leads must not appear in an estimate).
```
