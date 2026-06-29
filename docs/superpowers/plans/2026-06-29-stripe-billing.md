# Stripe Billing (Credit Packs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let buyers self-serve purchase one-time credit packs via Stripe Checkout, with credits granted only by a signature-verified, idempotent webhook through the existing credit ledger.

**Architecture:** A new `app/billing/` package (`packs` catalog, `stripe_gateway` = the only Stripe-importing module, `service` = idempotent fulfillment with no Stripe calls), a `StripePayment` model, and a `routes_billing` router with a buyer checkout route + an unauthenticated webhook. All Stripe calls sit behind `stripe_gateway` so tests monkeypatch it — no live calls, no Stripe account needed.

**Tech Stack:** Python 3.11 (`.venv/Scripts/python`), FastAPI/SQLModel, the `stripe` lib, reuse of `app.core.purchasing.grant_credits` + `CreditTransaction`. pytest + TestClient.

## Global Constraints

- Interpreter `.venv/Scripts/python`; tests `.venv/Scripts/python -m pytest`. Use Bash for git; no `cd` prefixes.
- **Credits are granted ONLY by the webhook → `fulfill_session` → `grant_credits`.** The success redirect never grants credits.
- **Idempotent:** `StripePayment.session_id` is UNIQUE; `fulfill_session` is a no-op if already `completed`. No double-credit on webhook retries/replays.
- **Mockable / test-mode:** the ONLY module importing `stripe` is `app/billing/stripe_gateway.py`. Tests monkeypatch `app.billing.stripe_gateway`. With `STRIPE_SECRET_KEY` unset, billing is **disabled** (friendly notice, no live calls) and the full suite still passes.
- Config from env (all optional): `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `BILLING_CURRENCY` (default `gbp`).
- `app/core/` must stay free of `energy/utility/osm/overpass` (grep stays clean). Do NOT commit `*.db`.
- TDD: failing test → minimal code → passing test → commit.

---

## File Structure

```
app/billing/
  __init__.py
  packs.py            # Pack dataclass, CREDIT_PACKS, get_pack(), currency()
  stripe_gateway.py   # is_enabled(), create_checkout_session(), construct_event() — only stripe import
  service.py          # record_pending(), fulfill_session() — idempotent; no stripe calls
app/core/db.py        # + StripePayment model (session_id UNIQUE)
app/web/routes_billing.py   # POST /app/billing/checkout (buyer) + POST /stripe/webhook (unauth)
app/web/routes_buyer.py     # /app/billing route extended (packs + history + status)
app/web/templates/billing.html  # packs/buy buttons + history + disabled notice + status banner
app/leadvault.py      # include billing router
.env.example          # + STRIPE_* + BILLING_CURRENCY
tests/test_billing.py
```

---

### Task 1: Dependency + StripePayment model + packs catalog

**Files:**
- Modify: `requirements.txt`, `app/core/db.py`
- Create: `app/billing/__init__.py`, `app/billing/packs.py`
- Test: `tests/test_billing.py`

**Interfaces:**
- Produces: `StripePayment` SQLModel (table `lv_stripe_payment`, UNIQUE `session_id`); `Pack` dataclass `(key, credits, amount_cents, label)`; `CREDIT_PACKS: list[Pack]`; `get_pack(key)->Pack|None`; `currency()->str` (from `BILLING_CURRENCY`, default `gbp`).

- [ ] **Step 1: Add the stripe dep to `requirements.txt`** (append)

```
stripe==10.10.0
```

- [ ] **Step 2: Write `tests/test_billing.py`**

```python
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session
from app.core.db import init_db, StripePayment
from app.billing.packs import get_pack, CREDIT_PACKS, currency


def test_packs_catalog_and_lookup():
    assert get_pack("pack_100").credits == 100
    assert get_pack("pack_1000").amount_cents == 19900
    assert get_pack("nope") is None
    assert {p.key for p in CREDIT_PACKS} == {"pack_100", "pack_500", "pack_1000"}


def test_currency_default_gbp(monkeypatch):
    monkeypatch.delenv("BILLING_CURRENCY", raising=False)
    assert currency() == "gbp"
    monkeypatch.setenv("BILLING_CURRENCY", "USD")
    assert currency() == "usd"


def test_stripe_payment_session_id_is_unique():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        s.add(StripePayment(session_id="cs_1", buyer_account_id=1, credits=100)); s.commit()
        s.add(StripePayment(session_id="cs_1", buyer_account_id=1, credits=100))
        try:
            s.commit()
            raised = False
        except IntegrityError:
            raised = True
        assert raised
```

- [ ] **Step 3: Install the dep + run the test (fails)**

Run: `.venv/Scripts/python -m pip install -r requirements.txt`
Run: `.venv/Scripts/python -m pytest tests/test_billing.py -q` → FAIL (ModuleNotFoundError / no StripePayment).

- [ ] **Step 4: Add `StripePayment` to `app/core/db.py`** (add near the other models; `UniqueConstraint` is already imported in this file)

```python
class StripePayment(SQLModel, table=True):
    __tablename__ = "lv_stripe_payment"
    __table_args__ = (UniqueConstraint("session_id", name="uq_lv_stripe_session"),)
    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(default="", index=True)
    buyer_account_id: int = Field(default=0, index=True)
    pack_key: str = ""
    credits: int = 0
    amount_cents: int = 0
    currency: str = "gbp"
    status: str = "pending"  # pending | completed
    created_at: str = Field(default_factory=_now)
    completed_at: str | None = None
```

- [ ] **Step 5: Create `app/billing/__init__.py`** (empty file).

- [ ] **Step 6: Create `app/billing/packs.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Pack:
    key: str
    credits: int
    amount_cents: int  # minor units (pence/cents)
    label: str


CREDIT_PACKS = [
    Pack("pack_100", 100, 2900, "100 credits"),
    Pack("pack_500", 500, 11900, "500 credits"),
    Pack("pack_1000", 1000, 19900, "1,000 credits"),
]


def get_pack(key: str) -> Pack | None:
    return next((p for p in CREDIT_PACKS if p.key == key), None)


def currency() -> str:
    return (os.getenv("BILLING_CURRENCY") or "gbp").lower()
```

- [ ] **Step 7: Run the test (passes)**

Run: `.venv/Scripts/python -m pytest tests/test_billing.py -q` → PASS (3 tests).

- [ ] **Step 8: Commit**

```bash
git add requirements.txt app/core/db.py app/billing/__init__.py app/billing/packs.py tests/test_billing.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(billing): stripe dep + StripePayment model + credit-pack catalog"
```

---

### Task 2: Stripe gateway (the only stripe-importing module)

**Files:**
- Create: `app/billing/stripe_gateway.py`
- Test: `tests/test_billing.py` (add)

**Interfaces:**
- Consumes: `Pack` from `app.billing.packs`.
- Produces:
  - `is_enabled() -> bool` (True iff `STRIPE_SECRET_KEY` is set)
  - `create_checkout_session(pack, buyer_account_id, success_url, cancel_url, currency) -> dict` returning `{"id": str, "url": str}`
  - `construct_event(payload: bytes, sig_header: str) -> dict` (verifies + returns the Stripe event)

- [ ] **Step 1: Add tests to `tests/test_billing.py`**

```python
def test_gateway_is_enabled_reflects_env(monkeypatch):
    from app.billing import stripe_gateway
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    assert stripe_gateway.is_enabled() is False
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    assert stripe_gateway.is_enabled() is True
```

- [ ] **Step 2: Run it (fails)**

Run: `.venv/Scripts/python -m pytest tests/test_billing.py::test_gateway_is_enabled_reflects_env -q` → FAIL.

- [ ] **Step 3: Create `app/billing/stripe_gateway.py`**

```python
from __future__ import annotations

import os


def is_enabled() -> bool:
    return bool(os.getenv("STRIPE_SECRET_KEY"))


def _client():
    import stripe  # imported lazily so the app runs without stripe configured
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    return stripe


def create_checkout_session(pack, buyer_account_id, success_url, cancel_url,
                            currency) -> dict:
    stripe = _client()
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": currency,
                "unit_amount": pack.amount_cents,
                "product_data": {"name": pack.label},
            },
            "quantity": 1,
        }],
        client_reference_id=str(buyer_account_id),
        metadata={"buyer_account_id": str(buyer_account_id),
                  "pack_key": pack.key, "credits": str(pack.credits)},
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return {"id": session.id, "url": session.url}


def construct_event(payload: bytes, sig_header: str) -> dict:
    stripe = _client()
    secret = os.getenv("STRIPE_WEBHOOK_SECRET") or ""
    return stripe.Webhook.construct_event(payload, sig_header, secret)
```

- [ ] **Step 4: Run the test (passes)**

Run: `.venv/Scripts/python -m pytest tests/test_billing.py::test_gateway_is_enabled_reflects_env -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add app/billing/stripe_gateway.py tests/test_billing.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(billing): stripe gateway (isolated stripe lib wrapper)"
```

---

### Task 3: Idempotent fulfillment service

**Files:**
- Create: `app/billing/service.py`
- Test: `tests/test_billing.py` (add)

**Interfaces:**
- Consumes: `StripePayment`, `_now` from `app.core.db`; `grant_credits`, `balance` from `app.core.purchasing`.
- Produces:
  - `record_pending(session, session_id, buyer_account_id, pack_key, credits, amount_cents, currency) -> StripePayment`
  - `fulfill_session(session, session_id, buyer_account_id, credits, pack_key="", amount_cents=0, currency="gbp") -> StripePayment` — idempotent: no-op if already `completed`; otherwise mark completed + `grant_credits(..., reason="stripe_purchase", ref=session_id)`.

- [ ] **Step 1: Add tests to `tests/test_billing.py`**

```python
def test_fulfill_grants_once_and_is_idempotent():
    from sqlmodel import Session, select
    from app.core.db import init_db, BuyerAccount, CreditTransaction
    from app.core.purchasing import balance
    from app.billing.service import fulfill_session
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba = BuyerAccount(company_name="A", credits=0); s.add(ba); s.commit(); s.refresh(ba)
        p1 = fulfill_session(s, "cs_1", ba.id, 100, "pack_100", 2900, "gbp")
        assert p1.status == "completed"
        assert balance(s, ba.id) == 100
        # replay (webhook retry) — must NOT double-credit
        p2 = fulfill_session(s, "cs_1", ba.id, 100)
        assert p2.id == p1.id
        assert balance(s, ba.id) == 100
        # exactly one credit ledger row for this session
        txns = s.exec(select(CreditTransaction).where(
            CreditTransaction.ref == "cs_1")).all()
        assert len(txns) == 1


def test_record_pending_creates_pending_row():
    from sqlmodel import Session
    from app.core.db import init_db, StripePayment
    from app.billing.service import record_pending
    engine = init_db("sqlite://")
    with Session(engine) as s:
        p = record_pending(s, "cs_2", 7, "pack_500", 500, 11900, "gbp")
        assert p.status == "pending" and p.buyer_account_id == 7
```

- [ ] **Step 2: Run it (fails)**

Run: `.venv/Scripts/python -m pytest tests/test_billing.py -k fulfill_or_pending -q` (or run the two named tests) → FAIL.

- [ ] **Step 3: Create `app/billing/service.py`**

```python
from __future__ import annotations

from sqlmodel import Session, select

from app.core.db import StripePayment, _now
from app.core.purchasing import grant_credits


def record_pending(session: Session, session_id: str, buyer_account_id: int,
                   pack_key: str, credits: int, amount_cents: int,
                   currency: str) -> StripePayment:
    pay = StripePayment(session_id=session_id, buyer_account_id=buyer_account_id,
                        pack_key=pack_key, credits=credits, amount_cents=amount_cents,
                        currency=currency, status="pending")
    session.add(pay)
    session.commit()
    session.refresh(pay)
    return pay


def fulfill_session(session: Session, session_id: str, buyer_account_id: int,
                    credits: int, pack_key: str = "", amount_cents: int = 0,
                    currency: str = "gbp") -> StripePayment:
    pay = session.exec(select(StripePayment).where(
        StripePayment.session_id == session_id)).first()
    if pay and pay.status == "completed":
        return pay  # idempotent — already fulfilled (webhook retry/replay)
    if not pay:
        pay = StripePayment(session_id=session_id, buyer_account_id=buyer_account_id,
                            pack_key=pack_key, credits=credits, amount_cents=amount_cents,
                            currency=currency, status="pending")
        session.add(pay)
        session.commit()
        session.refresh(pay)
    pay.status = "completed"
    pay.completed_at = _now()
    session.add(pay)
    grant_credits(session, buyer_account_id, credits, reason="stripe_purchase",
                  ref=session_id)
    session.commit()
    session.refresh(pay)
    return pay
```

- [ ] **Step 4: Run the tests (pass)**

Run: `.venv/Scripts/python -m pytest tests/test_billing.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add app/billing/service.py tests/test_billing.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(billing): idempotent fulfillment service (credits only via webhook)"
```

---

### Task 4: Billing routes (checkout + webhook) + page + wiring

**Files:**
- Create: `app/web/routes_billing.py`
- Modify: `app/web/routes_buyer.py` (billing route), `app/web/templates/billing.html`, `app/leadvault.py`, `.env.example`
- Test: `tests/test_billing.py` (add route tests)

**Interfaces:**
- Consumes: `stripe_gateway`, `packs`, `service.record_pending/fulfill_session`, `app.web.deps` (`get_session`, `current_user`, `redirect`, `templates`), `StripePayment`, `BuyerAccount`, `app.core.purchasing.balance`.
- Produces routes: `POST /app/billing/checkout` (buyer), `POST /stripe/webhook` (unauth); an extended `GET /app/billing`.

- [ ] **Step 1: Add route tests to `tests/test_billing.py`**

```python
import json
from fastapi.testclient import TestClient
import app.leadvault as lv
from app.billing import stripe_gateway


def _client():
    return TestClient(lv.app)


def _login_buyer(c):
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345"})


def test_checkout_disabled_redirects_with_notice(monkeypatch):
    monkeypatch.setattr(stripe_gateway, "is_enabled", lambda: False)
    c = _client(); _login_buyer(c)
    r = c.post("/app/billing/checkout", data={"pack_key": "pack_100"},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "status=disabled" in r.headers["location"]


def test_checkout_enabled_redirects_to_stripe_and_records_pending(monkeypatch):
    monkeypatch.setattr(stripe_gateway, "is_enabled", lambda: True)
    monkeypatch.setattr(stripe_gateway, "create_checkout_session",
                        lambda *a, **k: {"id": "cs_test_1",
                                         "url": "https://checkout.stripe.test/cs_test_1"})
    c = _client(); _login_buyer(c)
    r = c.post("/app/billing/checkout", data={"pack_key": "pack_100"},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "https://checkout.stripe.test/cs_test_1"
    # a pending StripePayment row exists for that session
    from sqlmodel import Session, select
    from app.core.db import StripePayment
    with Session(lv.engine) as s:
        p = s.exec(select(StripePayment).where(
            StripePayment.session_id == "cs_test_1")).first()
        assert p is not None and p.status == "pending" and p.credits == 100


def test_webhook_credits_buyer_idempotently(monkeypatch):
    from sqlmodel import Session, select
    from app.core.db import BuyerAccount, User, StripePayment
    # make a fresh buyer with known credits
    with Session(lv.engine) as s:
        ba = BuyerAccount(company_name="WH", credits=0); s.add(ba); s.commit(); s.refresh(ba)
        baid = ba.id
    event = {"type": "checkout.session.completed",
             "data": {"object": {"id": "cs_wh_1", "amount_total": 2900,
                                  "currency": "gbp",
                                  "metadata": {"buyer_account_id": str(baid),
                                               "pack_key": "pack_100", "credits": "100"}}}}
    monkeypatch.setattr(stripe_gateway, "construct_event", lambda payload, sig: event)
    c = _client()
    r1 = c.post("/stripe/webhook", content=b"{}",
                headers={"Stripe-Signature": "t=1,v1=x"})
    assert r1.status_code == 200
    r2 = c.post("/stripe/webhook", content=b"{}",
                headers={"Stripe-Signature": "t=1,v1=x"})  # replay
    assert r2.status_code == 200
    with Session(lv.engine) as s:
        assert s.get(BuyerAccount, baid).credits == 100  # credited once, not twice


def test_webhook_bad_signature_returns_400(monkeypatch):
    def boom(payload, sig):
        raise ValueError("bad sig")
    monkeypatch.setattr(stripe_gateway, "construct_event", boom)
    r = _client().post("/stripe/webhook", content=b"{}",
                       headers={"Stripe-Signature": "bad"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run them (fail)**

Run: `.venv/Scripts/python -m pytest tests/test_billing.py -q` → the route tests FAIL (no routes yet).

- [ ] **Step 3: Create `app/web/routes_billing.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Form, Header
from fastapi.responses import Response
from sqlmodel import Session

from app.billing import stripe_gateway, packs
from app.billing.service import record_pending, fulfill_session
from app.web.deps import get_session, current_user, redirect

router = APIRouter()


@router.post("/app/billing/checkout")
def checkout(request: Request, pack_key: str = Form(...),
             session: Session = Depends(get_session)):
    u = current_user(request, session)
    if not u or u.role != "buyer":
        return redirect("/login")
    pack = packs.get_pack(pack_key)
    if not pack:
        return redirect("/app/billing?status=badpack")
    if not stripe_gateway.is_enabled():
        return redirect("/app/billing?status=disabled")
    base = str(request.base_url).rstrip("/")
    try:
        sess = stripe_gateway.create_checkout_session(
            pack, u.buyer_account_id, f"{base}/app/billing?status=success",
            f"{base}/app/billing?status=cancel", packs.currency())
    except Exception:
        return redirect("/app/billing?status=error")
    record_pending(session, sess["id"], u.buyer_account_id, pack.key, pack.credits,
                   pack.amount_cents, packs.currency())
    return redirect(sess["url"])


@router.post("/stripe/webhook")
async def webhook(request: Request, stripe_signature: str = Header(default=""),
                  session: Session = Depends(get_session)):
    payload = await request.body()
    try:
        event = stripe_gateway.construct_event(payload, stripe_signature)
    except Exception:
        return Response(status_code=400)
    if event.get("type") == "checkout.session.completed":
        obj = event["data"]["object"]
        meta = obj.get("metadata") or {}
        fulfill_session(session, obj.get("id"),
                        int(meta.get("buyer_account_id", 0) or 0),
                        int(meta.get("credits", 0) or 0),
                        meta.get("pack_key", ""),
                        int(obj.get("amount_total") or 0),
                        obj.get("currency", "gbp"))
    return Response(status_code=200)
```

- [ ] **Step 4: Extend the buyer billing route in `app/web/routes_buyer.py`** — replace the existing `billing` handler with this version (it adds packs, history, status, and the enabled flag):

```python
@router.get("/billing")
def billing(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    from app.billing import packs as billing_packs, stripe_gateway
    from app.core.db import StripePayment
    txns = session.exec(select(CreditTransaction).where(
        CreditTransaction.buyer_account_id == u.buyer_account_id)).all()
    payments = session.exec(select(StripePayment).where(
        StripePayment.buyer_account_id == u.buyer_account_id)).all()
    return templates.TemplateResponse(request, "billing.html", {
        "request": request, "user": u,
        "credits": balance(session, u.buyer_account_id), "txns": txns,
        "packs": billing_packs.CREDIT_PACKS, "payments": payments,
        "billing_enabled": stripe_gateway.is_enabled(),
        "status": request.query_params.get("status", "")})
```
(`balance` is already imported in routes_buyer.py from `app.core.purchasing`; `select`/`CreditTransaction`/`templates`/`redirect` are already imported.)

- [ ] **Step 5: Replace `app/web/templates/billing.html`**

```html
{% extends "base.html" %}{% block body %}
<h1 class="text-xl font-semibold mb-4">Billing</h1>
{% if status == "success" %}<p class="text-sm text-emerald-700 mb-3">Payment received — your credits will appear shortly.</p>{% endif %}
{% if status in ("cancel","disabled","badpack","error") %}<p class="text-sm text-amber-700 mb-3">Checkout was not completed ({{ status }}).</p>{% endif %}
<div class="bg-white p-4 rounded-xl border mb-4"><div class="text-3xl font-bold text-emerald-600">{{ credits }}</div><div class="text-sm text-slate-500">Credits</div></div>

<h2 class="font-medium mb-2">Buy credits</h2>
{% if billing_enabled %}
<div class="grid grid-cols-3 gap-4 mb-6">
  {% for p in packs %}
  <div class="bg-white p-4 rounded-xl border text-center">
    <div class="text-2xl font-bold">{{ p.credits }}</div>
    <div class="text-sm text-slate-500 mb-3">{{ p.label }}</div>
    <form method="post" action="/app/billing/checkout"><input type="hidden" name="pack_key" value="{{ p.key }}"><button class="w-full bg-emerald-600 text-white rounded-lg py-2">Buy</button></form>
  </div>
  {% endfor %}
</div>
{% else %}
<p class="text-sm text-slate-500 mb-6">Card payments are not configured in this deployment — credits are admin-granted. (Set <code>STRIPE_SECRET_KEY</code> to enable.)</p>
{% endif %}

<h2 class="font-medium mb-2">Purchases</h2>
<div class="bg-white rounded-xl border overflow-auto mb-6"><table class="w-full text-sm"><thead class="bg-slate-100"><tr><th class="text-left p-2">When</th><th class="text-left p-2">Pack</th><th class="text-left p-2">Credits</th><th class="text-left p-2">Status</th></tr></thead>
<tbody>{% for p in payments %}<tr class="border-t"><td class="p-2">{{ p.created_at }}</td><td class="p-2">{{ p.pack_key }}</td><td class="p-2">{{ p.credits }}</td><td class="p-2">{{ p.status }}</td></tr>{% endfor %}</tbody></table></div>

<h2 class="font-medium mb-2">Credit ledger</h2>
<div class="bg-white rounded-xl border overflow-auto"><table class="w-full text-sm"><thead class="bg-slate-100"><tr><th class="text-left p-2">When</th><th class="text-left p-2">Delta</th><th class="text-left p-2">Reason</th><th class="text-left p-2">Ref</th></tr></thead>
<tbody>{% for t in txns %}<tr class="border-t"><td class="p-2">{{ t.created_at }}</td><td class="p-2">{{ t.delta }}</td><td class="p-2">{{ t.reason }}</td><td class="p-2">{{ t.ref }}</td></tr>{% endfor %}</tbody></table></div>
{% endblock %}
```

- [ ] **Step 6: Wire the billing router in `app/leadvault.py`** — add after the other `include_router` lines:

```python
from app.web.routes_billing import router as billing_router
app.include_router(billing_router)
```

- [ ] **Step 7: Add Stripe config to `.env.example`** (append)

```
# Optional Stripe billing (credit packs). Leave STRIPE_SECRET_KEY blank to disable.
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
BILLING_CURRENCY=gbp
```

- [ ] **Step 8: Run the suite (passes)**

Run: `.venv/Scripts/python -m pytest tests/test_billing.py -q` → all pass (incl. checkout disabled/enabled + webhook idempotent + bad-sig 400).
Then: `rm -f leadvault.db leadscraper.db` and `.venv/Scripts/python -m pytest -q` → full suite passes.

- [ ] **Step 9: Commit**

```bash
git add app/web/routes_billing.py app/web/routes_buyer.py app/web/templates/billing.html app/leadvault.py .env.example tests/test_billing.py
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "feat(billing): checkout + webhook routes, billing page packs/history, wiring"
```

---

### Task 5: Full verification + README

**Files:**
- Modify: `README.md`
- Test: full suite + grep.

- [ ] **Step 1: Add a billing section to `README.md`**

```markdown
### Billing (Stripe credit packs)

Buyers can buy credit packs via Stripe Checkout. It is OFF until configured:
- Set `STRIPE_SECRET_KEY` (test mode) to enable the Buy buttons.
- Set `STRIPE_WEBHOOK_SECRET` and point a Stripe webhook at `POST /stripe/webhook` for the
  `checkout.session.completed` event. **Credits are granted only by the verified webhook** (idempotent),
  never by the success redirect. With no key set, the Billing page shows a notice and credits remain
  admin-granted. `BILLING_CURRENCY` defaults to `gbp`.
```

- [ ] **Step 2: Grep + full suite**

Run: `grep -rinE "energy|utility|osm|overpass" app/core/` → prints nothing (CORE CLEAN).
Run: `rm -f leadvault.db leadscraper.db` then `.venv/Scripts/python -m pytest -q` → all pass, zero collection errors, zero warnings.

- [ ] **Step 3: Commit**

```bash
git add README.md
git -c user.name="Lead Scraper Dev" -c user.email="youssef.zaki@student.giu-uni.de" commit -m "docs: Stripe billing run/config instructions"
```

---

## Self-Review

**Spec coverage:**
- Credit packs (one-time), Stripe Checkout, mockable/test-mode → Tasks 1–4 ✓
- Credits only via webhook + idempotent (`StripePayment.session_id` UNIQUE, status check) → Task 3 + Task 4 webhook ✓
- `stripe_gateway` is the only stripe import; tests monkeypatch it → Task 2 + Task 4 ✓
- Disabled mode (no key ⇒ notice, suite green) → Task 4 (checkout + page) ✓
- Dynamic `price_data` (no pre-created Stripe products) → Task 2 ✓
- Webhook at `/stripe/webhook` unauth, signature-verified, bad-sig 400 → Task 4 ✓
- StripePayment model + reuse CreditTransaction ledger (`ref=session_id`) → Tasks 1, 3 ✓
- Config env (STRIPE_SECRET_KEY/WEBHOOK_SECRET/BILLING_CURRENCY) + .env.example → Task 4 ✓
- Acceptance criteria 1–6 → covered by the test set in Tasks 1–4 + the grep in Task 5 ✓

**Placeholder scan:** none — every step has runnable code/commands.

**Type consistency:** `fulfill_session(session, session_id, buyer_account_id, credits, pack_key="", amount_cents=0, currency="gbp")` and `record_pending(...)` signatures match across Tasks 3 and 4. `create_checkout_session(pack, buyer_account_id, success_url, cancel_url, currency) -> {"id","url"}` matches its call in Task 4. `StripePayment` fields used in tests/routes match Task 1's model. The webhook reads `event.get("type")`, `event["data"]["object"]`, `obj.get("metadata")` — consistent with the crafted test event and Stripe's dict-like Event.

**Note for the implementer:** the `test_webhook_*` tests create buyer accounts directly in `lv.engine` and rely on the seeded demo buyer for login; `leadvault.db` is gitignored and recreated on import — if a stale DB causes a schema error after adding `StripePayment`, `rm -f leadvault.db` and re-run (as Task 4 Step 8 already does).
