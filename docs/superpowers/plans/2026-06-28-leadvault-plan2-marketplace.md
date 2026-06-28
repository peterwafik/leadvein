# LeadVault Slice One — Plan 2: Marketplace & Buyer App

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Prerequisite: Plan 1 (inventory & intelligence backend) is complete** — its DB models, adapters, scoring, ingestion, and compliance primitives are imported here.

**Goal:** The authenticated buyer journey on top of Plan 1's inventory: register/login → build a Lead Recipe → masked previews → credit-unlock → Purchased Leads + CSV export, plus an admin dashboard that runs Plan 1's ingestion. Server-enforced masking and opt-out/suppression are the compliance guarantees.

**Architecture:** A new FastAPI app `app/leadvault.py` (session-cookie auth, Jinja2 + Tailwind-CDN dashboard), with vertical-free marketplace logic in `app/core/` (auth, recipes→query, masking, marketplace, purchasing, export) and thin web routers in `app/web/`. The old `app.main:app` (engine demo) is untouched.

**Tech Stack:** Python 3.11 (`.venv/Scripts/python`), FastAPI + Starlette SessionMiddleware, SQLModel/SQLite (`leadvault.db`), passlib[bcrypt], Jinja2, Tailwind CDN. pytest + FastAPI TestClient.

## Global Constraints

- Interpreter `.venv/Scripts/python`; tests `.venv/Scripts/python -m pytest`.
- **Source/category-agnostic core still holds:** no `energy`/`utility`/`osm`/`overpass` strings anywhere in `app/core/` (re-checked in Task 12). The marketplace never imports an adapter.
- **Server-enforced masking is non-negotiable:** no route or serializer may return business_name/phone/public_email/website_url/address for a lead the requesting buyer has **not** purchased. Enforced in `app/core/masking.py` + ownership checks.
- **Opt-out + suppression are filtered at search, purchase, AND export** (defense in depth).
- **Compliance acknowledgement** is required before a buyer's first purchase.
- **Business-level data only** — no personal decision-maker fields surfaced.
- New app entry is `app/leadvault.py`; DB file `leadvault.db` (gitignored; never commit). Session secret from env `LEADVAULT_SECRET` (dev default allowed).
- TDD; web tests use `fastapi.testclient.TestClient` (cookies persist → sessions work). No live network in tests.
- Reuse Plan 1 modules and the existing `app/engine/export.py` (`rows_to_csv`). Do not modify Plan 1 files except where a task says so.

---

## File Structure

```
app/
  core/
    auth.py          # password hashing, user create/authenticate
    recipes.py       # LeadRecipe filters -> matching Lead rows (vertical-free)
    masking.py       # mask_preview / unlock_view / assert_owned
    marketplace.py   # search (masked + suppression-filtered) + estimate
    purchasing.py    # credit ledger, unlock_lead (re-buy guard, comply, audit)
    export_leads.py  # CSV of a buyer's purchased leads
  web/
    deps.py          # current_user / require_buyer / require_admin / templates
    routes_auth.py   # register / login / logout
    routes_buyer.py  # dashboard, recipes, marketplace, purchased, suppression, billing
    routes_admin.py  # ingestion, leads, sources, categories, opt-outs, audit log
    templates/       # base.html + page templates (Tailwind CDN)
  leadvault.py       # FastAPI app: SessionMiddleware, templates, startup seed, routers
tests/
  test_auth.py, test_recipes_query.py, test_masking.py, test_marketplace.py,
  test_purchasing.py, test_export_leads.py, test_web_journey.py
```

---

### Task 1: Auth (hashing + user create/authenticate)

**Files:**
- Create: `app/core/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `User`, `BuyerAccount` from `app.core.db`.
- Produces: `hash_password(p)->str`, `verify_password(p,h)->bool`,
  `create_user(session, email, password, role="buyer", buyer_account_id=None)->User`,
  `authenticate(session, email, password)->User|None`, `get_user(session, user_id)->User|None`.

- [ ] **Step 1: Write `tests/test_auth.py`**

```python
from sqlmodel import Session
from app.core.db import init_db, BuyerAccount
from app.core.auth import (hash_password, verify_password, create_user,
                           authenticate, get_user)


def test_password_hash_roundtrip():
    h = hash_password("s3cret")
    assert h != "s3cret"
    assert verify_password("s3cret", h) is True
    assert verify_password("wrong", h) is False


def test_create_and_authenticate():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba = BuyerAccount(company_name="Acme", credits=0)
        s.add(ba); s.commit(); s.refresh(ba)
        u = create_user(s, "a@b.com", "pw", role="buyer", buyer_account_id=ba.id)
        assert u.id is not None and u.password_hash != "pw"
        assert authenticate(s, "a@b.com", "pw").id == u.id
        assert authenticate(s, "a@b.com", "bad") is None
        assert authenticate(s, "missing@b.com", "pw") is None
        assert get_user(s, u.id).email == "a@b.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_auth.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `app/core/auth.py`**

```python
from __future__ import annotations

from passlib.context import CryptContext
from sqlmodel import Session, select

from app.core.db import User

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(p: str) -> str:
    return _pwd.hash(p)


def verify_password(p: str, h: str) -> bool:
    try:
        return _pwd.verify(p, h)
    except Exception:
        return False


def create_user(session: Session, email: str, password: str, role: str = "buyer",
                buyer_account_id: int | None = None) -> User:
    u = User(email=email.strip().lower(), password_hash=hash_password(password),
             role=role, buyer_account_id=buyer_account_id)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def authenticate(session: Session, email: str, password: str) -> User | None:
    u = session.exec(select(User).where(User.email == email.strip().lower())).first()
    if u and verify_password(password, u.password_hash):
        return u
    return None


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_auth.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/auth.py tests/test_auth.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(core): auth (password hashing + user create/authenticate)"
```

---

### Task 2: Recipe filters → matching leads (vertical-free)

**Files:**
- Create: `app/core/recipes.py`
- Test: `tests/test_recipes_query.py`

**Interfaces:**
- Consumes: `Lead` from `app.core.db`.
- Produces:
  - `DEFAULT_FILTERS: dict` (keys: `categories[], city, region, country, require_phone, require_email, require_website, freshness_days, min_score, exclude_categories[]`).
  - `matching_leads(session, filters:dict, *, exclude_lead_ids:set=frozenset()) -> list[Lead]` — applies score/contact/location/category/freshness filters; excludes opted-out leads (`opt_out_status != "clear"`) and any `exclude_lead_ids`.

- [ ] **Step 1: Write `tests/test_recipes_query.py`**

```python
import json
from sqlmodel import Session
from app.core.db import init_db, Lead, _now
from app.core.recipes import matching_leads, DEFAULT_FILTERS


def _seed(s):
    s.add(Lead(business_name="Diner", category_keys_json=json.dumps(["restaurant"]),
               city="London", phone="1", website_url="https://a.com", score_total=80,
               date_last_verified=_now(), opt_out_status="clear"))
    s.add(Lead(business_name="Cafe", category_keys_json=json.dumps(["cafe"]),
               city="London", phone="", website_url="https://b.com", score_total=40,
               date_last_verified=_now(), opt_out_status="clear"))
    s.add(Lead(business_name="OptedOut", category_keys_json=json.dumps(["restaurant"]),
               city="London", phone="1", score_total=90, date_last_verified=_now(),
               opt_out_status="opted_out"))
    s.commit()


def test_filters_category_score_contact_and_optout():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        _seed(s)
        f = {**DEFAULT_FILTERS, "categories": ["restaurant"], "min_score": 50,
             "require_phone": True, "city": "London"}
        res = matching_leads(s, f)
        names = [l.business_name for l in res]
        assert names == ["Diner"]          # cafe (low score), optout excluded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_recipes_query.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `app/core/recipes.py`**

```python
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.db import Lead

DEFAULT_FILTERS = {
    "categories": [], "city": "", "region": "", "country": "",
    "require_phone": False, "require_email": False, "require_website": False,
    "freshness_days": 0, "min_score": 0, "exclude_categories": [],
}


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


def matching_leads(session: Session, filters: dict, *,
                   exclude_lead_ids: set = frozenset()) -> list[Lead]:
    f = {**DEFAULT_FILTERS, **(filters or {})}
    rows = session.exec(select(Lead).where(
        Lead.score_total >= int(f["min_score"]),
        Lead.opt_out_status == "clear")).all()
    cats = set(f["categories"] or [])
    excl = set(f["exclude_categories"] or [])
    out = []
    for l in rows:
        if l.id in exclude_lead_ids:
            continue
        lcats = set(json.loads(l.category_keys_json or "[]"))
        if cats and not (lcats & cats):
            continue
        if excl and (lcats & excl):
            continue
        if f["city"] and f["city"].lower() not in (l.city or "").lower():
            continue
        if f["region"] and f["region"].lower() not in (l.region or "").lower():
            continue
        if f["country"] and f["country"].lower() not in (l.country or "").lower():
            continue
        if f["require_phone"] and not l.phone:
            continue
        if f["require_email"] and not l.public_email:
            continue
        if f["require_website"] and not l.website_url:
            continue
        if int(f["freshness_days"]) > 0 and _days_since(l.date_last_verified) > int(f["freshness_days"]):
            continue
        out.append(l)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_recipes_query.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/recipes.py tests/test_recipes_query.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(core): recipe filters -> matching leads"
```

---

### Task 3: Masking serializers + ownership guard

**Files:**
- Create: `app/core/masking.py`
- Test: `tests/test_masking.py`

**Interfaces:**
- Consumes: `Lead`, `PurchasedLead` from `app.core.db`.
- Produces:
  - `mask_preview(lead:Lead) -> dict` — NEVER includes business_name/phone/public_email/website_url/address; includes category_keys, city, region, country, score_total, subscores, score_explanation (reason), has_phone/has_email/has_website booleans, price_credits, exclusivity_status, source_type(=source_name), freshness(date_last_verified).
  - `unlock_view(lead:Lead) -> dict` — full record incl. contact + source metadata.
  - `is_owned(session, buyer_account_id, lead_id) -> bool`
  - `assert_owned(session, buyer_account_id, lead_id) -> None` (raises `PermissionError` if not owned).

- [ ] **Step 1: Write `tests/test_masking.py`**

```python
import json
from sqlmodel import Session
from app.core.db import init_db, Lead, PurchasedLead
from app.core.masking import mask_preview, unlock_view, is_owned, assert_owned
import pytest


def test_preview_never_leaks_contact():
    lead = Lead(business_name="Secret Diner", category_keys_json=json.dumps(["restaurant"]),
                city="London", phone="+44 1", public_email="x@y.com",
                website_url="https://secret.com", score_total=80,
                subscores_json=json.dumps({"fit": 80}), score_explanation="because",
                source_name="OpenStreetMap (Overpass)", price_credits=3)
    p = mask_preview(lead)
    blob = json.dumps(p).lower()
    assert "secret diner" not in blob
    assert "secret.com" not in blob and "x@y.com" not in blob and "+44 1" not in blob
    assert p["has_phone"] is True and p["has_email"] is True and p["has_website"] is True
    assert p["score_total"] == 80 and p["reason"] == "because"
    assert p["city"] == "London" and p["price_credits"] == 3


def test_unlock_view_has_contact():
    lead = Lead(business_name="D", phone="+44 1", public_email="x@y.com",
                website_url="https://s.com", source_url="http://src", source_license="ODbL")
    u = unlock_view(lead)
    assert u["business_name"] == "D" and u["phone"] == "+44 1"
    assert u["source_license"] == "ODbL"


def test_ownership_guard():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        s.add(PurchasedLead(buyer_account_id=1, lead_id=5))
        s.commit()
        assert is_owned(s, 1, 5) is True
        assert is_owned(s, 2, 5) is False
        assert_owned(s, 1, 5)  # no raise
        with pytest.raises(PermissionError):
            assert_owned(s, 2, 5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_masking.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `app/core/masking.py`**

```python
from __future__ import annotations

import json

from sqlmodel import Session, select

from app.core.db import Lead, PurchasedLead


def mask_preview(lead: Lead) -> dict:
    return {
        "lead_id": lead.id,
        "category_keys": json.loads(lead.category_keys_json or "[]"),
        "city": lead.city, "region": lead.region, "country": lead.country,
        "score_total": lead.score_total,
        "subscores": json.loads(lead.subscores_json or "{}"),
        "reason": lead.score_explanation,
        "has_phone": bool(lead.phone), "has_email": bool(lead.public_email),
        "has_website": bool(lead.website_url),
        "price_credits": lead.price_credits,
        "exclusivity_status": lead.exclusivity_status,
        "source_type": lead.source_name,
        "freshness": lead.date_last_verified,
    }


def unlock_view(lead: Lead) -> dict:
    return {
        "lead_id": lead.id, "business_name": lead.business_name,
        "category_keys": json.loads(lead.category_keys_json or "[]"),
        "address_line1": lead.address_line1, "city": lead.city, "region": lead.region,
        "postal_code": lead.postal_code, "country": lead.country,
        "latitude": lead.latitude, "longitude": lead.longitude,
        "phone": lead.phone, "public_email": lead.public_email,
        "website_url": lead.website_url,
        "attributes": json.loads(lead.attributes_json or "{}"),
        "intent": json.loads(lead.intent_json or "{}"),
        "score_total": lead.score_total,
        "subscores": json.loads(lead.subscores_json or "{}"),
        "score_explanation": lead.score_explanation,
        "source_name": lead.source_name, "source_url": lead.source_url,
        "source_license": lead.source_license, "lawful_basis": lead.lawful_basis,
        "date_last_verified": lead.date_last_verified,
    }


def is_owned(session: Session, buyer_account_id: int, lead_id: int) -> bool:
    return session.exec(select(PurchasedLead).where(
        PurchasedLead.buyer_account_id == buyer_account_id,
        PurchasedLead.lead_id == lead_id)).first() is not None


def assert_owned(session: Session, buyer_account_id: int, lead_id: int) -> None:
    if not is_owned(session, buyer_account_id, lead_id):
        raise PermissionError(f"buyer {buyer_account_id} does not own lead {lead_id}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_masking.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/masking.py tests/test_masking.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(core): masking serializers + ownership guard"
```

---

### Task 4: Marketplace search + estimate (suppression-filtered)

**Files:**
- Create: `app/core/marketplace.py`
- Test: `tests/test_marketplace.py`

**Interfaces:**
- Consumes: `matching_leads`, `mask_preview`, `is_owned`, `is_suppressed` (`app.core.compliance`), `host_of`, `Lead`.
- Produces:
  - `search(session, buyer_account_id, filters:dict) -> list[dict]` — masked previews of matching leads, **excluding** any suppressed (buyer or global) lead, each annotated with `already_owned`.
  - `estimate(session, buyer_account_id, filters:dict) -> dict` — `{count, score_buckets:{"80+":n,"50-79":n,"<50":n}, sample:[masked...], total_price_credits}`.

- [ ] **Step 1: Write `tests/test_marketplace.py`**

```python
import json
from sqlmodel import Session
from app.core.db import (init_db, Lead, _now, SuppressionList, SuppressionEntry)
from app.core.marketplace import search, estimate
from app.core.recipes import DEFAULT_FILTERS


def _seed(s):
    s.add(Lead(business_name="Diner", category_keys_json=json.dumps(["restaurant"]),
               city="London", phone="1", website_url="https://keep.com", score_total=85,
               date_last_verified=_now(), price_credits=3))
    s.add(Lead(business_name="Suppressed", category_keys_json=json.dumps(["restaurant"]),
               city="London", phone="1", website_url="https://blocked.com",
               score_total=88, date_last_verified=_now(), price_credits=3))
    s.commit()
    lst = SuppressionList(buyer_account_id=1, name="mine")
    s.add(lst); s.commit(); s.refresh(lst)
    s.add(SuppressionEntry(list_id=lst.id, kind="domain", value="blocked.com"))
    s.commit()


def test_search_excludes_suppressed_and_masks():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        _seed(s)
        f = {**DEFAULT_FILTERS, "categories": ["restaurant"], "city": "London"}
        res = search(s, 1, f)
        assert len(res) == 1                       # suppressed one excluded
        blob = json.dumps(res).lower()
        assert "keep.com" not in blob and "diner" not in blob   # masked
        assert res[0]["score_total"] == 85
        est = estimate(s, 1, f)
        assert est["count"] == 1 and est["score_buckets"]["80+"] == 1
        assert est["total_price_credits"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_marketplace.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `app/core/marketplace.py`**

```python
from __future__ import annotations

from sqlmodel import Session

from app.core.compliance import is_suppressed, host_of
from app.core.masking import mask_preview, is_owned
from app.core.recipes import matching_leads


def _not_suppressed(session: Session, buyer_account_id: int, lead) -> bool:
    return not is_suppressed(session, buyer_account_id,
                             domain=host_of(lead.website_url), phone=lead.phone,
                             email=lead.public_email,
                             business_name=lead.business_name)


def search(session: Session, buyer_account_id: int, filters: dict) -> list[dict]:
    leads = matching_leads(session, filters)
    out = []
    for l in leads:
        if not _not_suppressed(session, buyer_account_id, l):
            continue
        preview = mask_preview(l)
        preview["already_owned"] = is_owned(session, buyer_account_id, l.id)
        out.append(preview)
    return out


def estimate(session: Session, buyer_account_id: int, filters: dict) -> dict:
    previews = search(session, buyer_account_id, filters)
    buckets = {"80+": 0, "50-79": 0, "<50": 0}
    for p in previews:
        s = p["score_total"]
        buckets["80+" if s >= 80 else "50-79" if s >= 50 else "<50"] += 1
    return {"count": len(previews), "score_buckets": buckets,
            "sample": previews[:10],
            "total_price_credits": sum(p["price_credits"] for p in previews)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_marketplace.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/marketplace.py tests/test_marketplace.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(core): marketplace search + estimate (masked, suppression-filtered)"
```

---

### Task 5: Purchasing (credits, unlock, re-buy guard, compliance)

**Files:**
- Create: `app/core/purchasing.py`
- Test: `tests/test_purchasing.py`

**Interfaces:**
- Consumes: `BuyerAccount`, `Lead`, `PurchasedLead`, `CreditTransaction` from db; `is_suppressed`, `is_opted_out`, `host_of`, `audit` from compliance.
- Produces:
  - exceptions `InsufficientCredits`, `LeadSuppressed`, `ComplianceNotAcknowledged` (all subclass `ValueError`).
  - `grant_credits(session, buyer_account_id, amount, reason="grant", ref="") -> None`
  - `balance(session, buyer_account_id) -> int`
  - `unlock_lead(session, user, lead_id) -> PurchasedLead` — requires `BuyerAccount.compliance_ack_at`; if already owned returns the existing purchase (no double charge); rejects suppressed/opted-out; rejects insufficient credits; else debits credits, creates `PurchasedLead`, increments `Lead.times_sold`, writes a `CreditTransaction` + `AuditLog`.

- [ ] **Step 1: Write `tests/test_purchasing.py`**

```python
import pytest
from sqlmodel import Session, select
from app.core.db import (init_db, BuyerAccount, User, Lead, PurchasedLead,
                         CreditTransaction, OptOutRequest, _now)
from app.core.purchasing import (grant_credits, balance, unlock_lead,
                                 InsufficientCredits, LeadSuppressed,
                                 ComplianceNotAcknowledged)


def _setup(s, credits=10, acked=True):
    ba = BuyerAccount(company_name="Acme", credits=0,
                      compliance_ack_at=_now() if acked else None)
    s.add(ba); s.commit(); s.refresh(ba)
    u = User(email="a@b.com", password_hash="x", role="buyer", buyer_account_id=ba.id)
    s.add(u); s.commit(); s.refresh(u)
    if credits:
        grant_credits(s, ba.id, credits)
    lead = Lead(business_name="D", website_url="https://d.com", phone="1",
                price_credits=3, date_last_verified=_now())
    s.add(lead); s.commit(); s.refresh(lead)
    return ba, u, lead


def test_unlock_debits_and_creates_purchase():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u, lead = _setup(s)
        p = unlock_lead(s, u, lead.id)
        assert isinstance(p, PurchasedLead)
        assert balance(s, ba.id) == 7
        assert s.get(Lead, lead.id).times_sold == 1


def test_rebuy_is_idempotent_no_double_charge():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u, lead = _setup(s)
        first = unlock_lead(s, u, lead.id)
        again = unlock_lead(s, u, lead.id)
        assert again.id == first.id
        assert balance(s, ba.id) == 7   # charged once


def test_insufficient_credits_blocked():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u, lead = _setup(s, credits=1)
        with pytest.raises(InsufficientCredits):
            unlock_lead(s, u, lead.id)


def test_compliance_ack_required():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u, lead = _setup(s, acked=False)
        with pytest.raises(ComplianceNotAcknowledged):
            unlock_lead(s, u, lead.id)


def test_suppressed_or_optout_blocked():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u, lead = _setup(s)
        s.add(OptOutRequest(kind="domain", value="d.com", applied=True))
        s.commit()
        with pytest.raises(LeadSuppressed):
            unlock_lead(s, u, lead.id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_purchasing.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `app/core/purchasing.py`**

```python
from __future__ import annotations

from sqlmodel import Session, select

from app.core.compliance import is_suppressed, is_opted_out, host_of, audit
from app.core.db import (BuyerAccount, Lead, PurchasedLead, CreditTransaction, _now)


class InsufficientCredits(ValueError):
    pass


class LeadSuppressed(ValueError):
    pass


class ComplianceNotAcknowledged(ValueError):
    pass


def grant_credits(session: Session, buyer_account_id: int, amount: int,
                  reason: str = "grant", ref: str = "") -> None:
    ba = session.get(BuyerAccount, buyer_account_id)
    ba.credits += amount
    session.add(ba)
    session.add(CreditTransaction(buyer_account_id=buyer_account_id, delta=amount,
                                  reason=reason, ref=ref))
    session.commit()


def balance(session: Session, buyer_account_id: int) -> int:
    ba = session.get(BuyerAccount, buyer_account_id)
    return ba.credits if ba else 0


def unlock_lead(session: Session, user, lead_id: int) -> PurchasedLead:
    ba = session.get(BuyerAccount, user.buyer_account_id)
    if not ba or not ba.compliance_ack_at:
        raise ComplianceNotAcknowledged("compliance acknowledgement required")
    existing = session.exec(select(PurchasedLead).where(
        PurchasedLead.buyer_account_id == ba.id,
        PurchasedLead.lead_id == lead_id)).first()
    if existing:
        return existing  # idempotent re-buy, no double charge
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise ValueError("lead not found")
    if (is_opted_out(session, domain=host_of(lead.website_url), phone=lead.phone,
                     email=lead.public_email)
            or is_suppressed(session, ba.id, domain=host_of(lead.website_url),
                             phone=lead.phone, email=lead.public_email,
                             business_name=lead.business_name)):
        raise LeadSuppressed("lead is suppressed or opted out")
    price = lead.price_credits
    if ba.credits < price:
        raise InsufficientCredits(f"need {price}, have {ba.credits}")
    ba.credits -= price
    session.add(ba)
    session.add(CreditTransaction(buyer_account_id=ba.id, delta=-price,
                                  reason="unlock", ref=f"lead:{lead_id}"))
    lead.times_sold += 1
    lead.last_sold_at = _now()
    session.add(lead)
    purchase = PurchasedLead(buyer_account_id=ba.id, lead_id=lead_id, price_credits=price)
    session.add(purchase)
    session.commit()
    session.refresh(purchase)
    audit(session, user.id, "unlock", "Lead", str(lead_id),
          {"price": price, "buyer_account_id": ba.id})
    return purchase
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_purchasing.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/core/purchasing.py tests/test_purchasing.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(core): purchasing — credits, unlock, re-buy guard, compliance gates"
```

---

### Task 6: Export purchased leads to CSV

**Files:**
- Create: `app/core/export_leads.py`
- Test: `tests/test_export_leads.py`

**Interfaces:**
- Consumes: `PurchasedLead`, `Lead` from db; `unlock_view` from masking; `audit`, `is_suppressed`, `host_of`, `is_opted_out` from compliance; existing `app.engine.export.rows_to_csv`.
- Produces:
  - `EXPORT_COLUMNS: list[str]`
  - `export_purchased_csv(session, user, columns:list[str]|None=None) -> bytes` — CSV of the buyer's purchased leads (full contact via `unlock_view`), **skipping** any now-suppressed/opted-out lead, writing an `AuditLog`.

- [ ] **Step 1: Write `tests/test_export_leads.py`**

```python
from sqlmodel import Session
from app.core.db import (init_db, BuyerAccount, User, Lead, PurchasedLead,
                         OptOutRequest, _now)
from app.core.export_leads import export_purchased_csv


def test_export_includes_owned_skips_optout():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba = BuyerAccount(company_name="A", credits=0); s.add(ba); s.commit(); s.refresh(ba)
        u = User(email="a@b.com", password_hash="x", buyer_account_id=ba.id)
        s.add(u); s.commit(); s.refresh(u)
        keep = Lead(business_name="Keep", phone="1", website_url="https://keep.com",
                    date_last_verified=_now())
        drop = Lead(business_name="Drop", phone="2", website_url="https://drop.com",
                    date_last_verified=_now())
        s.add(keep); s.add(drop); s.commit(); s.refresh(keep); s.refresh(drop)
        s.add(PurchasedLead(buyer_account_id=ba.id, lead_id=keep.id))
        s.add(PurchasedLead(buyer_account_id=ba.id, lead_id=drop.id))
        s.add(OptOutRequest(kind="domain", value="drop.com", applied=True))
        s.commit()
        csv_bytes = export_purchased_csv(s, u)
        text = csv_bytes.decode("utf-8")
        assert "Keep" in text and "keep.com" in text
        assert "Drop" not in text         # opted-out skipped at export
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_export_leads.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `app/core/export_leads.py`**

```python
from __future__ import annotations

from sqlmodel import Session, select

from app.core.compliance import audit, is_suppressed, is_opted_out, host_of
from app.core.db import PurchasedLead, Lead
from app.core.masking import unlock_view
from app.engine.export import rows_to_csv

EXPORT_COLUMNS = ["business_name", "phone", "public_email", "website_url",
                  "address_line1", "city", "region", "postal_code", "country",
                  "category_keys", "score_total", "score_explanation",
                  "source_name", "source_url", "source_license",
                  "date_last_verified", "lawful_basis"]


def export_purchased_csv(session: Session, user, columns: list[str] | None = None) -> bytes:
    cols = columns or EXPORT_COLUMNS
    ba_id = user.buyer_account_id
    purchases = session.exec(select(PurchasedLead).where(
        PurchasedLead.buyer_account_id == ba_id)).all()
    rows = []
    for p in purchases:
        lead = session.get(Lead, p.lead_id)
        if lead is None:
            continue
        if (is_opted_out(session, domain=host_of(lead.website_url), phone=lead.phone,
                         email=lead.public_email)
                or is_suppressed(session, ba_id, domain=host_of(lead.website_url),
                                 phone=lead.phone, email=lead.public_email,
                                 business_name=lead.business_name)):
            continue
        rows.append(unlock_view(lead))
    audit(session, user.id, "export", "BuyerAccount", str(ba_id),
          {"count": len(rows)})
    return rows_to_csv(cols, rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_export_leads.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/export_leads.py tests/test_export_leads.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(core): CSV export of purchased leads (compliance-filtered)"
```

---

### Task 7: Web app wiring (app + session + templates + deps + base layout)

**Files:**
- Create: `app/leadvault.py`, `app/web/deps.py`, `app/web/templates/base.html`, `app/web/templates/login.html`, `app/web/routes_auth.py`
- Test: `tests/test_web_journey.py` (started here; extended in Task 8–10)

**Interfaces:**
- Consumes: everything in `app.core.*`, `app.seed.seed_all`, Plan 1 DB init.
- Produces:
  - `app/leadvault.py`: FastAPI `app` with `SessionMiddleware`, Jinja2 `templates`, a module-level `engine = init_db("sqlite:///leadvault.db")`, startup that runs `seed_all` + ensures a seeded admin (`admin@leadvault.local` / env `LEADVAULT_ADMIN_PW` or `admin12345`) and a demo buyer (`buyer@demo.local`/`buyer12345`, 100 credits), mounts routers + `/static`.
  - `app/web/deps.py`: `get_session()` dependency (yields a `Session`), `current_user(request, session)`, `require_buyer`, `require_admin`, `templates` (Jinja2Templates), `login_user(request, user)`, `logout_user(request)`.
  - `routes_auth.py`: `GET /login`, `POST /login`, `GET /register`, `POST /register`, `GET /logout`.

- [ ] **Step 1: Write `tests/test_web_journey.py` (auth portion)**

```python
from fastapi.testclient import TestClient
import app.leadvault as lv


def client():
    return TestClient(lv.app)


def test_login_page_and_demo_buyer_login():
    c = client()
    assert c.get("/login").status_code == 200
    # demo buyer is seeded at startup
    r = c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345"},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    # session cookie now set; dashboard is reachable
    r2 = c.get("/app")
    assert r2.status_code == 200
    assert "Dashboard" in r2.text


def test_protected_route_redirects_anonymous():
    c = client()
    r = c.get("/app", follow_redirects=False)
    assert r.status_code in (302, 303)  # -> /login
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_web_journey.py -q`
Expected: FAIL (ModuleNotFoundError: app.leadvault).

- [ ] **Step 3: Create `app/web/deps.py`**

```python
from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.core.auth import get_user

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# the engine is created in app.leadvault and injected at import time
_engine = None


def set_engine(engine) -> None:
    global _engine
    _engine = engine


def get_session():
    with Session(_engine) as s:
        yield s


def login_user(request: Request, user) -> None:
    request.session["user_id"] = user.id


def logout_user(request: Request) -> None:
    request.session.pop("user_id", None)


def current_user(request: Request, session: Session):
    uid = request.session.get("user_id")
    return get_user(session, uid) if uid else None


def require_buyer(request: Request, session: Session):
    u = current_user(request, session)
    if not u:
        return None
    return u


def require_admin(request: Request, session: Session):
    u = current_user(request, session)
    if u and u.role == "admin":
        return u
    return None


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)
```

- [ ] **Step 4: Create `app/web/templates/base.html`**

```html
<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>LeadVault{% block title %}{% endblock %}</title>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 text-slate-800">
<div class="flex min-h-screen">
  {% if user %}
  <aside class="hidden md:flex w-56 flex-col bg-white border-r border-slate-200 p-4">
    <div class="text-lg font-semibold text-emerald-600 mb-6">LeadVault</div>
    <nav class="space-y-1 text-sm">
      {% if user.role == 'admin' %}
        <a href="/admin" class="block px-3 py-2 rounded-lg text-slate-600">Admin Overview</a>
        <a href="/admin/ingest" class="block px-3 py-2 rounded-lg text-slate-600">Ingestion</a>
        <a href="/admin/leads" class="block px-3 py-2 rounded-lg text-slate-600">Leads</a>
        <a href="/admin/sources" class="block px-3 py-2 rounded-lg text-slate-600">Sources</a>
        <a href="/admin/categories" class="block px-3 py-2 rounded-lg text-slate-600">Categories</a>
        <a href="/admin/optouts" class="block px-3 py-2 rounded-lg text-slate-600">Opt-outs</a>
        <a href="/admin/audit" class="block px-3 py-2 rounded-lg text-slate-600">Audit Log</a>
      {% else %}
        <a href="/app" class="block px-3 py-2 rounded-lg text-slate-600">Dashboard</a>
        <a href="/app/recipes" class="block px-3 py-2 rounded-lg text-slate-600">Lead Recipes</a>
        <a href="/app/marketplace" class="block px-3 py-2 rounded-lg text-slate-600">Marketplace</a>
        <a href="/app/purchased" class="block px-3 py-2 rounded-lg text-slate-600">Purchased Leads</a>
        <a href="/app/suppression" class="block px-3 py-2 rounded-lg text-slate-600">Suppression</a>
        <a href="/app/billing" class="block px-3 py-2 rounded-lg text-slate-600">Billing</a>
      {% endif %}
      <a href="/logout" class="block px-3 py-2 rounded-lg text-slate-400">Logout</a>
    </nav>
  </aside>
  {% endif %}
  <main class="flex-1 p-6">{% block body %}{% endblock %}</main>
</div>
</body></html>
```

- [ ] **Step 5: Create `app/web/templates/login.html`**

```html
{% extends "base.html" %}{% block body %}
<div class="max-w-sm mx-auto mt-20 bg-white p-6 rounded-xl border shadow-sm">
  <div class="text-xl font-semibold text-emerald-600 mb-4">LeadVault</div>
  {% if error %}<p class="text-red-600 text-sm mb-2">{{ error }}</p>{% endif %}
  <form method="post" action="/login" class="space-y-3">
    <input name="email" type="email" placeholder="Email" class="w-full border rounded-lg p-2" required>
    <input name="password" type="password" placeholder="Password" class="w-full border rounded-lg p-2" required>
    <button class="w-full bg-emerald-600 text-white rounded-lg py-2">Log in</button>
  </form>
  <p class="text-xs text-slate-500 mt-3">No account? <a href="/register" class="text-emerald-600 underline">Register</a></p>
</div>{% endblock %}
```

- [ ] **Step 6: Create `app/web/routes_auth.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Form
from sqlmodel import Session

from app.core.auth import authenticate, create_user
from app.core.db import BuyerAccount
from app.web.deps import (templates, get_session, current_user, login_user,
                          logout_user, redirect)

router = APIRouter()


@router.get("/login")
def login_page(request: Request, session: Session = Depends(get_session)):
    if current_user(request, session):
        return redirect("/app")
    return templates.TemplateResponse("login.html", {"request": request, "user": None})


@router.post("/login")
def login_submit(request: Request, email: str = Form(...), password: str = Form(...),
                 session: Session = Depends(get_session)):
    user = authenticate(session, email, password)
    if not user:
        return templates.TemplateResponse(
            "login.html", {"request": request, "user": None,
                           "error": "Invalid credentials"}, status_code=401)
    login_user(request, user)
    return redirect("/admin" if user.role == "admin" else "/app")


@router.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "user": None})


@router.post("/register")
def register_submit(request: Request, company: str = Form(...), email: str = Form(...),
                    password: str = Form(...), session: Session = Depends(get_session)):
    from sqlmodel import select
    from app.core.db import User
    if session.exec(select(User).where(User.email == email.strip().lower())).first():
        return templates.TemplateResponse(
            "register.html", {"request": request, "user": None,
                              "error": "Email already registered"}, status_code=400)
    ba = BuyerAccount(company_name=company, credits=0)
    session.add(ba); session.commit(); session.refresh(ba)
    user = create_user(session, email, password, role="buyer", buyer_account_id=ba.id)
    login_user(request, user)
    return redirect("/app")


@router.get("/logout")
def logout(request: Request):
    logout_user(request)
    return redirect("/login")
```

- [ ] **Step 7: Create `app/web/templates/register.html`**

```html
{% extends "base.html" %}{% block body %}
<div class="max-w-sm mx-auto mt-20 bg-white p-6 rounded-xl border shadow-sm">
  <div class="text-xl font-semibold text-emerald-600 mb-4">Create account</div>
  {% if error %}<p class="text-red-600 text-sm mb-2">{{ error }}</p>{% endif %}
  <form method="post" action="/register" class="space-y-3">
    <input name="company" placeholder="Company name" class="w-full border rounded-lg p-2" required>
    <input name="email" type="email" placeholder="Email" class="w-full border rounded-lg p-2" required>
    <input name="password" type="password" placeholder="Password" class="w-full border rounded-lg p-2" required>
    <button class="w-full bg-emerald-600 text-white rounded-lg py-2">Register</button>
  </form>
  <p class="text-xs text-slate-500 mt-3">Have an account? <a href="/login" class="text-emerald-600 underline">Log in</a></p>
</div>{% endblock %}
```

- [ ] **Step 8: Create `app/leadvault.py`**

```python
from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

from app.core.db import init_db, User, BuyerAccount
from app.core.auth import create_user
from app.seed import seed_all
from app.web import deps
from app.web.routes_auth import router as auth_router

app = FastAPI(title="LeadVault")
app.add_middleware(SessionMiddleware,
                   secret_key=os.getenv("LEADVAULT_SECRET", "dev-leadvault-secret"))

engine = init_db("sqlite:///leadvault.db")
deps.set_engine(engine)


def _seed_accounts() -> None:
    with Session(engine) as s:
        seed_all(s)
        if not s.exec(select(User).where(User.role == "admin")).first():
            create_user(s, "admin@leadvault.local",
                        os.getenv("LEADVAULT_ADMIN_PW", "admin12345"), role="admin")
        if not s.exec(select(User).where(User.email == "buyer@demo.local")).first():
            ba = BuyerAccount(company_name="Demo Buyer", credits=100)
            s.add(ba); s.commit(); s.refresh(ba)
            create_user(s, "buyer@demo.local", "buyer12345", role="buyer",
                        buyer_account_id=ba.id)


_seed_accounts()

app.include_router(auth_router)


@app.get("/")
def root():
    return RedirectResponse("/login", status_code=303)
```

- [ ] **Step 9: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_web_journey.py -q`
Expected: the two tests in this task PASS. (`/app` 303-redirects for anonymous; after login it should 200 — that route is added in Task 8, so if `test_login...` fails on `/app` not existing yet, it is delivered in Task 8. To keep Task 7 self-contained, the `test_login_page_and_demo_buyer_login` assertion on `/app` is added in Task 8; in Task 7 assert only that `/login` works and POST `/login` returns 303 and sets a cookie.)

> Implementer note: in Task 7, trim `test_login_page_and_demo_buyer_login` to assert only
> `c.get("/login").status_code == 200` and the POST returns 303. Re-add the `/app` assertion
> in Task 8 once the buyer dashboard route exists.

- [ ] **Step 10: Commit**

```bash
git add app/leadvault.py app/web/deps.py app/web/routes_auth.py app/web/templates/base.html app/web/templates/login.html app/web/templates/register.html tests/test_web_journey.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(web): LeadVault app shell — session auth, base layout, login/register"
```

---

### Task 8: Buyer routes — dashboard, recipes, marketplace, purchased, billing, suppression

**Files:**
- Create: `app/web/routes_buyer.py`, templates `dashboard.html`, `recipes.html`, `marketplace.html`, `purchased.html`, `billing.html`, `suppression.html`, `compliance_ack.html`
- Modify: `app/leadvault.py` (include buyer router)
- Test: extend `tests/test_web_journey.py`

**Interfaces:**
- Consumes: `current_user`, `get_session`, `templates`, `redirect`; `marketplace.search/estimate`, `recipes.DEFAULT_FILTERS`, `masking.unlock_view`, `masking.assert_owned`, `purchasing.unlock_lead/balance`, `export_leads.export_purchased_csv`, `compliance.audit`, db models.
- Produces buyer routes under `/app`:
  - `GET /app` (dashboard) · `GET /app/recipes` + `POST /app/recipes` (save) ·
    `GET /app/marketplace` (form + search results from a recipe or ad-hoc filters) ·
    `POST /app/marketplace/search` · `POST /app/unlock/{lead_id}` ·
    `GET /app/purchased` · `GET /app/purchased/{lead_id}` (full detail; `assert_owned`) ·
    `GET /app/export.csv` · `GET /app/billing` · `GET /app/suppression` +
    `POST /app/suppression` (add entry) · `GET /app/ack` + `POST /app/ack` (compliance ack).
  - All `/app/*` redirect to `/login` if anonymous; redirect to `/app/ack` if no
    `compliance_ack_at` and the action requires it (unlock/export).

- [ ] **Step 1: Extend `tests/test_web_journey.py`** (append; full buyer journey)

```python
def test_full_buyer_journey(monkeypatch):
    from sqlmodel import Session
    import json
    from app.core.db import Lead, _now
    # seed one matching lead directly into the app DB
    with Session(lv.engine) as s:
        s.add(Lead(business_name="Hidden Diner",
                   category_keys_json=json.dumps(["restaurant"]), city="London",
                   phone="+44 1", public_email="info@diner.com",
                   website_url="https://hiddendiner.co.uk", score_total=85,
                   subscores_json=json.dumps({"fit": 85}),
                   score_explanation="independent restaurant, open 7 days",
                   source_name="OpenStreetMap (Overpass)", source_url="http://osm",
                   source_license="ODbL", date_last_verified=_now(), price_credits=3))
        s.commit()
    c = client()
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345"})
    # marketplace search returns a MASKED card (no business name / contact)
    r = c.post("/app/marketplace/search",
               data={"categories": "restaurant", "city": "London", "min_score": "50"})
    assert r.status_code == 200
    assert "Hidden Diner" not in r.text and "hiddendiner.co.uk" not in r.text
    assert "85" in r.text  # score visible
    # accept compliance, then unlock
    c.post("/app/ack")
    lead_id = None
    with Session(lv.engine) as s:
        from sqlmodel import select
        lead_id = s.exec(select(Lead).where(Lead.business_name == "Hidden Diner")).first().id
    ru = c.post(f"/app/unlock/{lead_id}", follow_redirects=False)
    assert ru.status_code in (302, 303)
    # purchased detail now shows full contact
    detail = c.get(f"/app/purchased/{lead_id}")
    assert detail.status_code == 200
    assert "Hidden Diner" in detail.text and "info@diner.com" in detail.text
    # export contains the unlocked contact
    ex = c.get("/app/export.csv")
    assert ex.status_code == 200 and "info@diner.com" in ex.text
    # a different buyer cannot view the detail (ownership guard)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_web_journey.py::test_full_buyer_journey -q`
Expected: FAIL.

- [ ] **Step 3: Implement `app/web/routes_buyer.py`**

```python
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import Response
from sqlmodel import Session, select

from app.core.compliance import audit
from app.core.db import (BuyerAccount, Lead, LeadRecipe, PurchasedLead,
                         SuppressionList, SuppressionEntry, CreditTransaction, _now)
from app.core.export_leads import export_purchased_csv
from app.core.marketplace import search, estimate
from app.core.masking import unlock_view, assert_owned
from app.core.purchasing import (unlock_lead, balance, InsufficientCredits,
                                 LeadSuppressed, ComplianceNotAcknowledged)
from app.core.recipes import DEFAULT_FILTERS
from app.web.deps import templates, get_session, current_user, redirect

router = APIRouter(prefix="/app")


def _buyer(request: Request, session: Session):
    u = current_user(request, session)
    if not u or u.role != "buyer":
        return None
    return u


def _filters_from_form(form) -> dict:
    cats = [c.strip() for c in (form.get("categories", "") or "").split(",") if c.strip()]
    return {**DEFAULT_FILTERS, "categories": cats, "city": form.get("city", ""),
            "min_score": int(form.get("min_score") or 0),
            "require_phone": form.get("require_phone") == "on",
            "require_website": form.get("require_website") == "on",
            "freshness_days": int(form.get("freshness_days") or 0)}


@router.get("")
def dashboard(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    ba = session.get(BuyerAccount, u.buyer_account_id)
    n_purchased = len(session.exec(select(PurchasedLead).where(
        PurchasedLead.buyer_account_id == ba.id)).all())
    n_recipes = len(session.exec(select(LeadRecipe).where(
        LeadRecipe.buyer_account_id == ba.id)).all())
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": u, "credits": ba.credits,
        "n_purchased": n_purchased, "n_recipes": n_recipes,
        "acked": bool(ba.compliance_ack_at)})


@router.get("/marketplace")
def marketplace_page(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    return templates.TemplateResponse("marketplace.html", {
        "request": request, "user": u, "results": None})


@router.post("/marketplace/search")
async def marketplace_search(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    form = await request.form()
    filters = _filters_from_form(form)
    results = search(session, u.buyer_account_id, filters)
    est = estimate(session, u.buyer_account_id, filters)
    return templates.TemplateResponse("marketplace.html", {
        "request": request, "user": u, "results": results, "estimate": est,
        "credits": balance(session, u.buyer_account_id)})


@router.post("/unlock/{lead_id}")
def unlock(request: Request, lead_id: int, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    try:
        unlock_lead(session, u, lead_id)
    except ComplianceNotAcknowledged:
        return redirect("/app/ack")
    except (InsufficientCredits, LeadSuppressed):
        return redirect("/app/marketplace")
    return redirect("/app/purchased")


@router.get("/purchased")
def purchased(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    purchases = session.exec(select(PurchasedLead).where(
        PurchasedLead.buyer_account_id == u.buyer_account_id)).all()
    rows = [unlock_view(session.get(Lead, p.lead_id)) | {"status": p.status,
            "purchased_at": p.purchased_at} for p in purchases if session.get(Lead, p.lead_id)]
    return templates.TemplateResponse("purchased.html", {
        "request": request, "user": u, "rows": rows})


@router.get("/purchased/{lead_id}")
def purchased_detail(request: Request, lead_id: int,
                     session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    try:
        assert_owned(session, u.buyer_account_id, lead_id)
    except PermissionError:
        return redirect("/app/purchased")
    audit(session, u.id, "view_detail", "Lead", str(lead_id), {})
    lead = unlock_view(session.get(Lead, lead_id))
    return templates.TemplateResponse("lead_detail.html", {
        "request": request, "user": u, "lead": lead})


@router.get("/export.csv")
def export_csv(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    data = export_purchased_csv(session, u)
    return Response(content=data, media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="leads.csv"'})


@router.get("/ack")
def ack_page(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    return templates.TemplateResponse("compliance_ack.html", {"request": request, "user": u})


@router.post("/ack")
def ack_submit(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    ba = session.get(BuyerAccount, u.buyer_account_id)
    ba.compliance_ack_at = _now()
    session.add(ba); session.commit()
    audit(session, u.id, "compliance_ack", "BuyerAccount", str(ba.id), {})
    return redirect("/app/marketplace")


@router.get("/recipes")
def recipes_page(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    recs = session.exec(select(LeadRecipe).where(
        LeadRecipe.buyer_account_id == u.buyer_account_id)).all()
    return templates.TemplateResponse("recipes.html", {
        "request": request, "user": u, "recipes": recs})


@router.post("/recipes")
async def recipes_save(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    form = await request.form()
    rec = LeadRecipe(buyer_account_id=u.buyer_account_id,
                     name=form.get("name", "Recipe"),
                     filters_json=json.dumps(_filters_from_form(form)),
                     scoring_profile_key=form.get("scoring_profile_key", "utility_energy"))
    session.add(rec); session.commit()
    return redirect("/app/recipes")


@router.get("/billing")
def billing(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    txns = session.exec(select(CreditTransaction).where(
        CreditTransaction.buyer_account_id == u.buyer_account_id)).all()
    return templates.TemplateResponse("billing.html", {
        "request": request, "user": u, "credits": balance(session, u.buyer_account_id),
        "txns": txns})


@router.get("/suppression")
def suppression_page(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    lists = session.exec(select(SuppressionList).where(
        SuppressionList.buyer_account_id == u.buyer_account_id)).all()
    entries = []
    for lst in lists:
        entries += session.exec(select(SuppressionEntry).where(
            SuppressionEntry.list_id == lst.id)).all()
    return templates.TemplateResponse("suppression.html", {
        "request": request, "user": u, "entries": entries})


@router.post("/suppression")
async def suppression_add(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    form = await request.form()
    lst = session.exec(select(SuppressionList).where(
        SuppressionList.buyer_account_id == u.buyer_account_id)).first()
    if not lst:
        lst = SuppressionList(buyer_account_id=u.buyer_account_id, name="default")
        session.add(lst); session.commit(); session.refresh(lst)
    session.add(SuppressionEntry(list_id=lst.id, kind=form.get("kind", "domain"),
                                 value=form.get("value", "").strip().lower()))
    session.commit()
    return redirect("/app/suppression")
```

- [ ] **Step 4: Create the buyer templates**

`dashboard.html`:
```html
{% extends "base.html" %}{% block body %}
<h1 class="text-xl font-semibold mb-4">Dashboard</h1>
<div class="grid grid-cols-3 gap-4">
  <div class="bg-white p-4 rounded-xl border"><div class="text-3xl font-bold text-emerald-600">{{ credits }}</div><div class="text-sm text-slate-500">Credits</div></div>
  <div class="bg-white p-4 rounded-xl border"><div class="text-3xl font-bold">{{ n_purchased }}</div><div class="text-sm text-slate-500">Purchased leads</div></div>
  <div class="bg-white p-4 rounded-xl border"><div class="text-3xl font-bold">{{ n_recipes }}</div><div class="text-sm text-slate-500">Saved recipes</div></div>
</div>
{% if not acked %}<p class="mt-4 text-sm text-amber-700">You must accept the compliance terms before your first purchase. <a class="underline" href="/app/ack">Review &amp; accept</a></p>{% endif %}
{% endblock %}
```

`marketplace.html`:
```html
{% extends "base.html" %}{% block body %}
<h1 class="text-xl font-semibold mb-4">Marketplace</h1>
<form method="post" action="/app/marketplace/search" class="bg-white p-4 rounded-xl border grid grid-cols-2 gap-3 mb-4 text-sm">
  <label>Categories (comma-sep)<input name="categories" class="mt-1 w-full border rounded-lg p-2" placeholder="restaurant, cafe"></label>
  <label>City<input name="city" class="mt-1 w-full border rounded-lg p-2" placeholder="London"></label>
  <label>Min score<input name="min_score" type="number" value="50" class="mt-1 w-full border rounded-lg p-2"></label>
  <label>Freshness (days, 0=any)<input name="freshness_days" type="number" value="0" class="mt-1 w-full border rounded-lg p-2"></label>
  <label class="flex items-center gap-2"><input type="checkbox" name="require_phone"> Require phone</label>
  <label class="flex items-center gap-2"><input type="checkbox" name="require_website"> Require website</label>
  <button class="col-span-2 bg-emerald-600 text-white rounded-lg py-2">Search</button>
</form>
{% if results is not none %}
<p class="text-sm text-slate-600 mb-3">{{ estimate.count }} matching · {{ estimate.score_buckets['80+'] }} high-score · est. {{ estimate.total_price_credits }} credits to unlock all. Credits: {{ credits }}.</p>
<div class="grid grid-cols-3 gap-4">
  {% for r in results %}
  <div class="bg-white p-4 rounded-xl border">
    <div class="flex justify-between"><span class="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">{{ r.score_total }}</span><span class="text-xs text-slate-400">{{ r.source_type }}</span></div>
    <div class="mt-2 text-sm font-medium">{{ r.category_keys|join(', ') }}</div>
    <div class="text-xs text-slate-500">{{ r.city }} · {{ r.country }}</div>
    <div class="mt-1 text-xs text-slate-500">{% if r.has_phone %}☎{% endif %} {% if r.has_email %}✉{% endif %} {% if r.has_website %}🌐{% endif %}</div>
    <div class="mt-2 text-xs text-slate-600">{{ r.reason }}</div>
    <div class="mt-3 flex justify-between items-center">
      <span class="text-sm">{{ r.price_credits }} credits</span>
      {% if r.already_owned %}<span class="text-xs text-emerald-600">Owned</span>
      {% else %}<form method="post" action="/app/unlock/{{ r.lead_id }}"><button class="text-sm bg-emerald-600 text-white rounded-lg px-3 py-1">Unlock</button></form>{% endif %}
    </div>
  </div>
  {% endfor %}
</div>
{% endif %}
{% endblock %}
```

`purchased.html`:
```html
{% extends "base.html" %}{% block body %}
<div class="flex justify-between mb-4"><h1 class="text-xl font-semibold">Purchased Leads</h1>
<a href="/app/export.csv" class="text-sm border rounded-lg px-3 py-1">Export CSV</a></div>
<div class="bg-white rounded-xl border overflow-auto"><table class="w-full text-sm">
<thead class="bg-slate-100"><tr><th class="text-left p-2">Business</th><th class="text-left p-2">City</th><th class="text-left p-2">Phone</th><th class="text-left p-2">Email</th><th class="text-left p-2">Score</th><th class="text-left p-2">Status</th><th></th></tr></thead>
<tbody>{% for r in rows %}<tr class="border-t"><td class="p-2">{{ r.business_name }}</td><td class="p-2">{{ r.city }}</td><td class="p-2">{{ r.phone }}</td><td class="p-2">{{ r.public_email }}</td><td class="p-2">{{ r.score_total }}</td><td class="p-2">{{ r.status }}</td><td class="p-2"><a class="text-emerald-600 underline" href="/app/purchased/{{ r.lead_id }}">View</a></td></tr>{% endfor %}</tbody>
</table></div>{% endblock %}
```

`lead_detail.html`:
```html
{% extends "base.html" %}{% block body %}
<a href="/app/purchased" class="text-sm text-slate-500">&larr; Purchased</a>
<h1 class="text-xl font-semibold my-3">{{ lead.business_name }}</h1>
<div class="grid grid-cols-2 gap-4">
  <div class="bg-white p-4 rounded-xl border text-sm space-y-1">
    <div><b>Phone:</b> {{ lead.phone }}</div><div><b>Email:</b> {{ lead.public_email }}</div>
    <div><b>Website:</b> <a class="text-emerald-600 underline" href="{{ lead.website_url }}" target="_blank" rel="noopener">{{ lead.website_url }}</a></div>
    <div><b>Address:</b> {{ lead.address_line1 }}, {{ lead.city }} {{ lead.postal_code }} {{ lead.country }}</div>
    <div><b>Category:</b> {{ lead.category_keys|join(', ') }}</div>
  </div>
  <div class="bg-white p-4 rounded-xl border text-sm space-y-1">
    <div><b>Score:</b> {{ lead.score_total }} — {{ lead.score_explanation }}</div>
    <div><b>Source:</b> {{ lead.source_name }}</div>
    <div><b>Source URL:</b> <a class="text-emerald-600 underline" href="{{ lead.source_url }}" target="_blank" rel="noopener">{{ lead.source_url }}</a></div>
    <div><b>License:</b> {{ lead.source_license }}</div>
    <div><b>Lawful basis:</b> {{ lead.lawful_basis }}</div>
    <div><b>Verified:</b> {{ lead.date_last_verified }}</div>
  </div>
</div>{% endblock %}
```

`billing.html`:
```html
{% extends "base.html" %}{% block body %}
<h1 class="text-xl font-semibold mb-4">Billing</h1>
<div class="bg-white p-4 rounded-xl border mb-4"><div class="text-3xl font-bold text-emerald-600">{{ credits }}</div><div class="text-sm text-slate-500">Credits (admin-granted in this release)</div></div>
<div class="bg-white rounded-xl border overflow-auto"><table class="w-full text-sm"><thead class="bg-slate-100"><tr><th class="text-left p-2">When</th><th class="text-left p-2">Delta</th><th class="text-left p-2">Reason</th><th class="text-left p-2">Ref</th></tr></thead>
<tbody>{% for t in txns %}<tr class="border-t"><td class="p-2">{{ t.created_at }}</td><td class="p-2">{{ t.delta }}</td><td class="p-2">{{ t.reason }}</td><td class="p-2">{{ t.ref }}</td></tr>{% endfor %}</tbody></table></div>{% endblock %}
```

`suppression.html`:
```html
{% extends "base.html" %}{% block body %}
<h1 class="text-xl font-semibold mb-4">Suppression</h1>
<form method="post" action="/app/suppression" class="bg-white p-4 rounded-xl border flex gap-3 mb-4 text-sm">
  <select name="kind" class="border rounded-lg p-2"><option value="domain">domain</option><option value="phone">phone</option><option value="email">email</option><option value="business_name">business name</option></select>
  <input name="value" class="border rounded-lg p-2 flex-1" placeholder="value to suppress" required>
  <button class="bg-emerald-600 text-white rounded-lg px-3 py-1">Add</button>
</form>
<div class="bg-white rounded-xl border overflow-auto"><table class="w-full text-sm"><thead class="bg-slate-100"><tr><th class="text-left p-2">Kind</th><th class="text-left p-2">Value</th></tr></thead>
<tbody>{% for e in entries %}<tr class="border-t"><td class="p-2">{{ e.kind }}</td><td class="p-2">{{ e.value }}</td></tr>{% endfor %}</tbody></table></div>{% endblock %}
```

`recipes.html`:
```html
{% extends "base.html" %}{% block body %}
<h1 class="text-xl font-semibold mb-4">Lead Recipes</h1>
<form method="post" action="/app/recipes" class="bg-white p-4 rounded-xl border grid grid-cols-2 gap-3 mb-4 text-sm">
  <label>Name<input name="name" class="mt-1 w-full border rounded-lg p-2" required></label>
  <label>Scoring profile<input name="scoring_profile_key" value="utility_energy" class="mt-1 w-full border rounded-lg p-2"></label>
  <label>Categories<input name="categories" class="mt-1 w-full border rounded-lg p-2" placeholder="restaurant, cafe"></label>
  <label>City<input name="city" class="mt-1 w-full border rounded-lg p-2"></label>
  <label>Min score<input name="min_score" type="number" value="50" class="mt-1 w-full border rounded-lg p-2"></label>
  <label class="flex items-center gap-2 mt-5"><input type="checkbox" name="require_phone"> Require phone</label>
  <button class="col-span-2 bg-emerald-600 text-white rounded-lg py-2">Save recipe</button>
</form>
<div class="space-y-2">{% for r in recipes %}<div class="bg-white p-3 rounded-xl border text-sm">{{ r.name }} — profile {{ r.scoring_profile_key }}</div>{% endfor %}</div>{% endblock %}
```

`compliance_ack.html`:
```html
{% extends "base.html" %}{% block body %}
<div class="max-w-lg mx-auto bg-white p-6 rounded-xl border mt-10 text-sm">
  <h1 class="text-lg font-semibold mb-3">Compliance acknowledgement</h1>
  <ul class="list-disc pl-5 space-y-1 text-slate-600">
    <li>I am responsible for lawful B2B outreach and will respect opt-outs.</li>
    <li>I will not use these leads for spam and will follow applicable marketing law.</li>
    <li>I will use suppression lists and will not resell leads unless permitted.</li>
    <li>I understand data is business-level, from lawful public/official/licensed sources with attribution.</li>
  </ul>
  <form method="post" action="/app/ack" class="mt-4"><button class="bg-emerald-600 text-white rounded-lg px-4 py-2">I acknowledge</button></form>
</div>{% endblock %}
```

- [ ] **Step 5: Wire the buyer router in `app/leadvault.py`** — add after the auth router include:

```python
from app.web.routes_buyer import router as buyer_router
app.include_router(buyer_router)
```

- [ ] **Step 6: Run the journey test**

Run: `.venv/Scripts/python -m pytest tests/test_web_journey.py -q`
Expected: PASS (auth tests + `test_full_buyer_journey`). Restore the `/app` assertion in `test_login_page_and_demo_buyer_login` now that the dashboard exists.

- [ ] **Step 7: Commit**

```bash
git add app/web/routes_buyer.py app/web/templates app/leadvault.py tests/test_web_journey.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(web): buyer journey — recipes, masked marketplace, unlock, purchased, export, suppression, ack"
```

---

### Task 9: Admin routes — ingestion, leads, sources, categories, opt-outs, audit, grant credits

**Files:**
- Create: `app/web/routes_admin.py`, templates `admin_overview.html`, `admin_ingest.html`, `admin_leads.html`, `admin_sources.html`, `admin_categories.html`, `admin_optouts.html`, `admin_audit.html`
- Modify: `app/leadvault.py` (include admin router)
- Test: extend `tests/test_web_journey.py` (admin ingestion via fake adapter)

**Interfaces:**
- Consumes: `require_admin`/`current_user`, `ingestion.pipeline.ingest`, `adapters.registry`, `taxonomy`, `purchasing.grant_credits`, db models, `compliance.audit`.
- Produces admin routes under `/admin`: `GET /admin` · `GET/POST /admin/ingest` (runs `ingest` with chosen adapter key + area + categories + profile) · `GET /admin/leads` · `GET /admin/sources` · `GET /admin/categories` + `POST /admin/categories` (add) · `GET /admin/optouts` + `POST /admin/optouts` (add opt-out) · `GET /admin/audit` · `POST /admin/grant` (grant credits to a buyer account). All redirect to `/login` if not admin.

- [ ] **Step 1: Extend `tests/test_web_journey.py`** (append; admin ingestion with a fake adapter registered into the app)

```python
def test_admin_ingestion_populates_inventory(monkeypatch):
    from app.adapters.base import SourceMeta, NormalizedLead
    from app.adapters import registry as adapter_registry

    class FakeAdminAdapter:
        meta = SourceMeta(key="fake_admin", name="FakeAdmin", type="test",
                          url="http://x", license="TESTLIC")
        def discover(self, query):
            return [{"n": "Admin Diner"}]
        def normalize(self, raw):
            return NormalizedLead(business_name=raw["n"], category_keys=["restaurant"],
                                  address={"city": "London"}, phone="+44 9",
                                  website_url="https://admindiner.com",
                                  source_key=self.meta.key, source_license=self.meta.license)
        def attribution(self):
            return "fake"

    adapter_registry.register(FakeAdminAdapter())
    # avoid live website enrichment during the test
    import app.web.routes_admin as ra
    monkeypatch.setattr(ra, "_enrich_for_admin",
                        lambda lead: {"website_reachable": True, "ssl": True,
                                      "online_ordering_detected": False,
                                      "booking_detected": False,
                                      "payment_provider_detected": False,
                                      "ecommerce_detected": False,
                                      "last_scanned": "2026-06-28T00:00:00+00:00"})
    c = client()
    c.post("/login", data={"email": "admin@leadvault.local", "password": "admin12345"})
    r = c.post("/admin/ingest", data={"adapter_key": "fake_admin", "city": "London",
               "categories": "restaurant", "scoring_profile_key": "utility_energy"},
               follow_redirects=True)
    assert r.status_code == 200
    assert "Admin Diner" in r.text or "1" in r.text  # leads list or count shows the new lead
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_web_journey.py::test_admin_ingestion_populates_inventory -q`
Expected: FAIL.

- [ ] **Step 3: Implement `app/web/routes_admin.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Form
from sqlmodel import Session, select

from app.adapters import registry as adapter_registry
from app.adapters.base import AdapterQuery
from app.core.compliance import audit
from app.core.db import (Lead, LeadSource, AuditLog, OptOutRequest, IngestionJob,
                         BuyerAccount)
from app.core.taxonomy import all_categories, upsert_category
from app.core.purchasing import grant_credits
from app.enrich.website import enrich_website
from app.ingestion.pipeline import ingest
from app.web.deps import templates, get_session, current_user, redirect

router = APIRouter(prefix="/admin")


def _admin(request: Request, session: Session):
    u = current_user(request, session)
    return u if (u and u.role == "admin") else None


def _enrich_for_admin(lead):  # indirection so tests can stub out live website enrichment
    return enrich_website(lead)


@router.get("")
def overview(request: Request, session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    n_leads = len(session.exec(select(Lead)).all())
    n_sources = len(session.exec(select(LeadSource)).all())
    return templates.TemplateResponse("admin_overview.html", {
        "request": request, "user": u, "n_leads": n_leads, "n_sources": n_sources})


@router.get("/ingest")
def ingest_page(request: Request, session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    return templates.TemplateResponse("admin_ingest.html", {
        "request": request, "user": u, "adapters": adapter_registry.all_keys(),
        "result": None})


@router.post("/ingest")
def ingest_run(request: Request, adapter_key: str = Form(...), city: str = Form(""),
               categories: str = Form(""),
               scoring_profile_key: str = Form("utility_energy"),
               session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    cats = [c.strip() for c in categories.split(",") if c.strip()]
    adapter = adapter_registry.get(adapter_key)
    counts = ingest(session, adapter,
                    AdapterQuery(area={"city": city}, categories=cats, limit=100),
                    scoring_profile_key=scoring_profile_key,
                    enrich_fn=_enrich_for_admin, actor_user_id=u.id)
    return templates.TemplateResponse("admin_ingest.html", {
        "request": request, "user": u, "adapters": adapter_registry.all_keys(),
        "result": counts})


@router.get("/leads")
def leads(request: Request, session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    rows = session.exec(select(Lead).order_by(Lead.id.desc())).all()[:200]
    return templates.TemplateResponse("admin_leads.html", {
        "request": request, "user": u, "rows": rows})


@router.get("/sources")
def sources(request: Request, session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    rows = session.exec(select(LeadSource)).all()
    return templates.TemplateResponse("admin_sources.html", {
        "request": request, "user": u, "rows": rows})


@router.get("/categories")
def categories(request: Request, session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    return templates.TemplateResponse("admin_categories.html", {
        "request": request, "user": u, "cats": all_categories(session)})


@router.post("/categories")
def categories_add(request: Request, key: str = Form(...), label: str = Form(...),
                   session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    upsert_category(session, key.strip(), label.strip())
    return redirect("/admin/categories")


@router.get("/optouts")
def optouts(request: Request, session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    rows = session.exec(select(OptOutRequest)).all()
    return templates.TemplateResponse("admin_optouts.html", {
        "request": request, "user": u, "rows": rows})


@router.post("/optouts")
def optouts_add(request: Request, kind: str = Form(...), value: str = Form(...),
                session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    session.add(OptOutRequest(kind=kind, value=value.strip().lower(), applied=True))
    session.commit()
    audit(session, u.id, "optout_add", "OptOutRequest", value, {"kind": kind})
    return redirect("/admin/optouts")


@router.post("/grant")
def grant(request: Request, buyer_account_id: int = Form(...), amount: int = Form(...),
          session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    grant_credits(session, buyer_account_id, amount, reason="admin_grant")
    audit(session, u.id, "grant_credits", "BuyerAccount", str(buyer_account_id),
          {"amount": amount})
    return redirect("/admin")


@router.get("/audit")
def audit_page(request: Request, session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    rows = session.exec(select(AuditLog).order_by(AuditLog.id.desc())).all()[:200]
    return templates.TemplateResponse("admin_audit.html", {
        "request": request, "user": u, "rows": rows})
```

- [ ] **Step 4: Create admin templates**

`admin_overview.html`:
```html
{% extends "base.html" %}{% block body %}
<h1 class="text-xl font-semibold mb-4">Admin Overview</h1>
<div class="grid grid-cols-2 gap-4">
  <div class="bg-white p-4 rounded-xl border"><div class="text-3xl font-bold">{{ n_leads }}</div><div class="text-sm text-slate-500">Leads in inventory</div></div>
  <div class="bg-white p-4 rounded-xl border"><div class="text-3xl font-bold">{{ n_sources }}</div><div class="text-sm text-slate-500">Sources</div></div>
</div>
<form method="post" action="/admin/grant" class="bg-white p-4 rounded-xl border mt-4 flex gap-3 text-sm items-end">
  <label>Buyer account id<input name="buyer_account_id" type="number" class="mt-1 block border rounded-lg p-2"></label>
  <label>Credits<input name="amount" type="number" class="mt-1 block border rounded-lg p-2"></label>
  <button class="bg-emerald-600 text-white rounded-lg px-3 py-2">Grant credits</button>
</form>{% endblock %}
```

`admin_ingest.html`:
```html
{% extends "base.html" %}{% block body %}
<h1 class="text-xl font-semibold mb-4">Ingestion</h1>
<form method="post" action="/admin/ingest" class="bg-white p-4 rounded-xl border grid grid-cols-2 gap-3 text-sm">
  <label>Source adapter<select name="adapter_key" class="mt-1 w-full border rounded-lg p-2">{% for a in adapters %}<option>{{ a }}</option>{% endfor %}</select></label>
  <label>Scoring profile<input name="scoring_profile_key" value="utility_energy" class="mt-1 w-full border rounded-lg p-2"></label>
  <label>City / area<input name="city" class="mt-1 w-full border rounded-lg p-2" placeholder="London"></label>
  <label>Categories<input name="categories" class="mt-1 w-full border rounded-lg p-2" placeholder="restaurant, cafe, gym"></label>
  <button class="col-span-2 bg-emerald-600 text-white rounded-lg py-2">Run ingestion</button>
</form>
{% if result %}<p class="mt-3 text-sm text-slate-700">Discovered {{ result.discovered }}, stored {{ result.stored }}, duplicates {{ result.skipped_duplicate }}, compliance-skipped {{ result.skipped_compliance }}. <a class="text-emerald-600 underline" href="/admin/leads">View leads</a></p>{% endif %}
{% endblock %}
```

`admin_leads.html`:
```html
{% extends "base.html" %}{% block body %}
<h1 class="text-xl font-semibold mb-4">Leads ({{ rows|length }})</h1>
<div class="bg-white rounded-xl border overflow-auto"><table class="w-full text-sm"><thead class="bg-slate-100"><tr><th class="text-left p-2">Business</th><th class="text-left p-2">City</th><th class="text-left p-2">Score</th><th class="text-left p-2">Source</th><th class="text-left p-2">License</th><th class="text-left p-2">Opt-out</th></tr></thead>
<tbody>{% for l in rows %}<tr class="border-t"><td class="p-2">{{ l.business_name }}</td><td class="p-2">{{ l.city }}</td><td class="p-2">{{ l.score_total }}</td><td class="p-2">{{ l.source_name }}</td><td class="p-2">{{ l.source_license }}</td><td class="p-2">{{ l.opt_out_status }}</td></tr>{% endfor %}</tbody></table></div>{% endblock %}
```

`admin_sources.html`:
```html
{% extends "base.html" %}{% block body %}
<h1 class="text-xl font-semibold mb-4">Sources</h1>
<div class="bg-white rounded-xl border overflow-auto"><table class="w-full text-sm"><thead class="bg-slate-100"><tr><th class="text-left p-2">Key</th><th class="text-left p-2">Name</th><th class="text-left p-2">Type</th><th class="text-left p-2">License</th><th class="text-left p-2">Terms</th></tr></thead>
<tbody>{% for s in rows %}<tr class="border-t"><td class="p-2">{{ s.key }}</td><td class="p-2">{{ s.name }}</td><td class="p-2">{{ s.type }}</td><td class="p-2">{{ s.license }}</td><td class="p-2">{{ s.terms_status }}</td></tr>{% endfor %}</tbody></table></div>{% endblock %}
```

`admin_categories.html`:
```html
{% extends "base.html" %}{% block body %}
<h1 class="text-xl font-semibold mb-4">Categories</h1>
<form method="post" action="/admin/categories" class="bg-white p-4 rounded-xl border flex gap-3 mb-4 text-sm">
  <input name="key" placeholder="key (e.g. florist)" class="border rounded-lg p-2" required>
  <input name="label" placeholder="Label (e.g. Florist)" class="border rounded-lg p-2" required>
  <button class="bg-emerald-600 text-white rounded-lg px-3 py-1">Add / update</button>
</form>
<div class="bg-white rounded-xl border overflow-auto"><table class="w-full text-sm"><thead class="bg-slate-100"><tr><th class="text-left p-2">Key</th><th class="text-left p-2">Label</th></tr></thead>
<tbody>{% for c in cats %}<tr class="border-t"><td class="p-2">{{ c.key }}</td><td class="p-2">{{ c.label }}</td></tr>{% endfor %}</tbody></table></div>{% endblock %}
```

`admin_optouts.html`:
```html
{% extends "base.html" %}{% block body %}
<h1 class="text-xl font-semibold mb-4">Opt-out requests</h1>
<form method="post" action="/admin/optouts" class="bg-white p-4 rounded-xl border flex gap-3 mb-4 text-sm">
  <select name="kind" class="border rounded-lg p-2"><option value="domain">domain</option><option value="phone">phone</option><option value="email">email</option></select>
  <input name="value" placeholder="value" class="border rounded-lg p-2 flex-1" required>
  <button class="bg-emerald-600 text-white rounded-lg px-3 py-1">Apply opt-out</button>
</form>
<div class="bg-white rounded-xl border overflow-auto"><table class="w-full text-sm"><thead class="bg-slate-100"><tr><th class="text-left p-2">Kind</th><th class="text-left p-2">Value</th><th class="text-left p-2">Applied</th></tr></thead>
<tbody>{% for o in rows %}<tr class="border-t"><td class="p-2">{{ o.kind }}</td><td class="p-2">{{ o.value }}</td><td class="p-2">{{ o.applied }}</td></tr>{% endfor %}</tbody></table></div>{% endblock %}
```

`admin_audit.html`:
```html
{% extends "base.html" %}{% block body %}
<h1 class="text-xl font-semibold mb-4">Audit Log</h1>
<div class="bg-white rounded-xl border overflow-auto"><table class="w-full text-sm"><thead class="bg-slate-100"><tr><th class="text-left p-2">When</th><th class="text-left p-2">Actor</th><th class="text-left p-2">Action</th><th class="text-left p-2">Entity</th><th class="text-left p-2">Id</th></tr></thead>
<tbody>{% for a in rows %}<tr class="border-t"><td class="p-2">{{ a.created_at }}</td><td class="p-2">{{ a.actor_user_id }}</td><td class="p-2">{{ a.action }}</td><td class="p-2">{{ a.entity }}</td><td class="p-2">{{ a.entity_id }}</td></tr>{% endfor %}</tbody></table></div>{% endblock %}
```

- [ ] **Step 5: Wire the admin router in `app/leadvault.py`** — add:

```python
from app.web.routes_admin import router as admin_router
app.include_router(admin_router)
```

- [ ] **Step 6: Run the admin test**

Run: `.venv/Scripts/python -m pytest tests/test_web_journey.py::test_admin_ingestion_populates_inventory -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/web/routes_admin.py app/web/templates app/leadvault.py tests/test_web_journey.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(web): admin — ingestion, leads, sources, categories, opt-outs, audit, grant credits"
```

---

### Task 10: End-to-end verification, grep acceptance, README, manual run

**Files:**
- Modify: `README.md`
- Test: full suite + manual run.

**Interfaces:** none new.

- [ ] **Step 1: Add a LeadVault section to `README.md`**

```markdown
## LeadVault (compliant B2B lead marketplace)

Run the marketplace app:
\`\`\`bash
.venv/Scripts/python -m uvicorn app.leadvault:app --reload
\`\`\`
Open http://127.0.0.1:8000 → /login. Seeded accounts:
- Admin: \`admin@leadvault.local\` / \`admin12345\` (set \`LEADVAULT_ADMIN_PW\` to override)
- Demo buyer: \`buyer@demo.local\` / \`buyer12345\` (100 credits)

Flow: admin → Ingestion (pick \`osm_overpass\`, a city, categories) → buyer → Marketplace
(masked previews) → Unlock (credits) → Purchased Leads → Export CSV. Every lead carries its
source, license (e.g. ODbL/OpenStreetMap), and verification date; opt-out/suppression are
filtered at search, purchase, and export; all unlocks/exports are in the admin Audit Log.
```

- [ ] **Step 2: GREP ACCEPTANCE — core still source/vertical-free**

Run:
```bash
grep -rinE "energy|utility|osm|overpass" app/core/ && echo "LEAK" || echo "CORE CLEAN"
```
Expected: `CORE CLEAN`.

- [ ] **Step 3: Run the full test suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all Plan 1 + Plan 2 tests pass, plus the pre-existing engine tests.

- [ ] **Step 4: Manual smoke run**

Run: `.venv/Scripts/python -m uvicorn app.leadvault:app` then in a browser:
1. Log in as admin → Ingestion → adapter `osm_overpass`, city "Manchester", categories
   "restaurant, cafe, gym" → Run (live Overpass; returns real businesses).
2. Log in as the demo buyer → Marketplace → categories "restaurant", city "Manchester",
   min score 50 → Search → see **masked** cards (score + reason, no contact).
3. Accept compliance → Unlock a lead → Purchased Leads → open detail (full contact + source +
   license + verification) → Export CSV.
4. Add a suppression entry (a domain you saw) → re-search → that lead is gone.

Expected: masked previews never show contact; unlock debits credits; purchased detail shows
full record + ODbL attribution; export contains only owned, non-suppressed leads; admin Audit
Log shows the unlock/export.

- [ ] **Step 5: Commit**

```bash
git add README.md
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "docs: LeadVault run instructions + slice-one acceptance"
```

---

## Self-Review

**Spec coverage (slice-one design, marketplace half):**
- Real lightweight auth (hashed pw, session cookie, buyer/admin) → Tasks 1, 7 ✓
- Recipe builder + filter→query → Tasks 2, 8 ✓
- Masked preview vs unlock (server-enforced) → Tasks 3, 8 (search masks; detail asserts ownership) ✓
- Credit-unlock + re-buy guard + insufficient/suppressed/ack gates → Tasks 5, 8 ✓
- Purchased leads + status + CSV export (compliance-filtered) → Tasks 6, 8 ✓
- Suppression upload + opt-out, filtered at search/purchase/export → Tasks 4, 5, 6, 8, 9 ✓
- Buyer compliance acknowledgement before first purchase → Tasks 5, 8 ✓
- Admin: run ingestion (calls Plan 1 `ingest`), leads, sources, categories, opt-outs, audit,
  grant credits → Task 9 ✓
- Source/license/verification metadata shown per lead; audit on unlock/export/admin → Tasks 3, 8, 9 ✓
- Business-level data only (no personal fields surfaced) → masking/unlock views ✓
- Grep-clean core → Task 10 Step 2 ✓
- Runs locally `uvicorn app.leadvault:app` → Tasks 7–10 ✓

**Placeholder scan:** none. (Task 7 Step 9 contains an explicit implementer note about trimming
one assertion to keep the task self-contained; the assertion is restored in Task 8 Step 6 — that
is sequencing guidance, not a placeholder.)

**Type consistency:** `unlock_lead(session, user, lead_id)`, `mask_preview(lead)`,
`unlock_view(lead)`, `search(session, buyer_account_id, filters)`,
`matching_leads(session, filters)`, `export_purchased_csv(session, user)` are used identically
across tasks. `current_user/get_session/templates/redirect` come from `app.web.deps`. Exceptions
`InsufficientCredits/LeadSuppressed/ComplianceNotAcknowledged` are caught in Task 8 exactly as
defined in Task 5. The buyer/admin routers are both included in `app/leadvault.py`.

**Cross-plan dependency:** Plan 2 imports Plan 1's `app.core.db` models, `app.seed.seed_all`,
`app.ingestion.pipeline.ingest`, `app.adapters.registry`, `app.core.compliance`,
`app.core.taxonomy`, `app.enrich.website`, and `app.scoring.*`. Plan 1 must be complete first.
