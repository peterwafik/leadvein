# LeadVault — Stripe Billing (Credit Packs) Design

**Date:** 2026-06-29
**Status:** Approved (brainstorming).
**Scope:** First billing slice — buyers self-serve purchase one-time credit packs via Stripe Checkout.

---

## 1. Goal

Turn admin-granted credits into **self-serve purchases**. A buyer buys a fixed credit pack via
Stripe's hosted Checkout; on a signature-verified webhook, credits are added through the existing
`CreditTransaction` ledger. No card data touches our server. **Credits are granted ONLY by the
webhook**, never by the success redirect (which a user can fake). Idempotent against webhook
retries/replays.

Decisions (from brainstorming): **credit packs (one-time)**; **Stripe Checkout (hosted)**;
**mockable + test-mode** (builds and tests green with no Stripe account; real test keys drop in
via env).

---

## 2. Architecture (isolated, testable)

```
app/billing/
  __init__.py
  packs.py            # CREDIT_PACKS catalog + get_pack(key)
  stripe_gateway.py   # the ONLY module that calls the stripe lib
  service.py          # fulfill_session(...) — idempotent credit grant; NO stripe calls
app/core/db.py        # + StripePayment model (session_id UNIQUE)
app/web/routes_billing.py  # POST /app/billing/checkout (buyer) + POST /stripe/webhook (unauth)
app/web/routes_buyer.py    # billing page extended to show packs + purchase history
app/web/templates/billing.html  # packs + buy buttons + history + disabled notice
app/leadvault.py      # include the billing router
```

The split keeps payment logic out of the marketplace core and isolates the one Stripe dependency:
- `stripe_gateway.py` — `is_enabled() -> bool`, `create_checkout_session(pack, buyer_account_id,
  success_url, cancel_url) -> {"id", "url"}`, `construct_event(payload: bytes, sig_header: str) ->
  dict`. Reads `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` at call time. This is the only file
  that imports `stripe`; tests monkeypatch it so there are **no live calls**.
- `service.py` — `fulfill_session(session, session_id, buyer_account_id, credits) -> StripePayment`
  is the idempotent core, fully unit-testable without Stripe.

---

## 3. Data flow

1. **Billing page** (`GET /app/billing`) lists `CREDIT_PACKS` with Buy buttons + the buyer's
   `StripePayment` history + current balance. If `stripe_gateway.is_enabled()` is False, buttons are
   replaced with "Card payments not configured — credits are admin-granted in this deployment."
2. **Checkout** (`POST /app/billing/checkout`, form `pack_key`): buyer-only route. Looks up the pack;
   if billing disabled → redirect back with a notice. Else create a Stripe Checkout Session
   (`mode=payment`, one `line_item` using dynamic `price_data` = `{currency, unit_amount:
   pack.amount_cents, product_data:{name}}`, `quantity:1`), with `client_reference_id =
   buyer_account_id` and `metadata = {buyer_account_id, pack_key, credits}`, `success_url =
   <base>/app/billing?status=success`, `cancel_url = <base>/app/billing?status=cancel`. Record a
   `StripePayment(session_id, buyer_account_id, pack_key, credits, amount_cents, currency,
   status="pending")`, then redirect (303) to `session.url`. Dynamic `price_data` means **no
   pre-created Stripe products** are required.
3. Buyer pays on Stripe's page → redirected to `success_url`. The page just shows a "payment
   received, credits will appear shortly" banner — it does NOT grant credits.
4. **Webhook** (`POST /stripe/webhook`, unauthenticated; signature IS the auth): read the raw body +
   `Stripe-Signature` header → `construct_event` (verifies against `STRIPE_WEBHOOK_SECRET`). On
   `checkout.session.completed`, extract `session_id` + `metadata` and call
   `service.fulfill_session(...)`. Return 200. On signature failure → 400. Unknown event types →
   200 (ignored).

---

## 4. Idempotency (the core correctness requirement)

`StripePayment.session_id` has a **UNIQUE constraint** (same DB-enforced discipline as
`PurchasedLead`). `fulfill_session`:
- If a `StripePayment` for `session_id` exists and `status == "completed"` → return it, **no credit,
  no-op** (replay/retry safe).
- Else mark it `completed` (or create it if the webhook somehow arrives with no pending record —
  the webhook is the source of truth), set `completed_at`, and call `grant_credits(session,
  buyer_account_id, credits, reason="stripe_purchase", ref=session_id)` (one `CreditTransaction`).
- The unique constraint + the status check together prevent double-crediting under retries or
  concurrent deliveries.

---

## 5. Data model (added to `app/core/db.py`)

`StripePayment` (`lv_stripe_payment`): `id`, `session_id` (UNIQUE, indexed), `buyer_account_id`
(indexed), `pack_key`, `credits`, `amount_cents`, `currency`, `status` (`pending` | `completed`),
`created_at`, `completed_at` (nullable). The credit grant itself reuses the existing
`CreditTransaction` ledger (`ref = session_id`).

---

## 6. Credit packs (`app/billing/packs.py`)

Code-defined for the MVP (DB-editable packs are a follow-up). Currency from `BILLING_CURRENCY`
(default `gbp`). Seeded packs:

| key | credits | amount | display |
|---|---|---|---|
| `pack_100` | 100 | 2900 | 100 credits — £29 |
| `pack_500` | 500 | 11900 | 500 credits — £119 |
| `pack_1000` | 1000 | 19900 | 1,000 credits — £199 |

`get_pack(key) -> Pack | None`. `amount` is in the currency's minor unit (pence/cents).

---

## 7. Config (env, all optional)

- `STRIPE_SECRET_KEY` — unset ⇒ billing disabled (no live calls, friendly notice).
- `STRIPE_WEBHOOK_SECRET` — required to verify webhooks; unset ⇒ webhook returns 400.
- `BILLING_CURRENCY` — default `gbp`.
- Base URL for success/cancel is derived from the incoming request (`request.base_url`).
- Added to `.env.example`.

---

## 8. Security

- No card data on our server (hosted Checkout).
- Webhook verified via `STRIPE_WEBHOOK_SECRET`; unverified ⇒ 400, no credit.
- `/app/billing/checkout` is buyer-authenticated; `/stripe/webhook` is intentionally unauthenticated
  (Stripe calls it) and trusts ONLY the verified signature + the metadata in the verified event.
- Credits flow only through the webhook → `fulfill_session` → `grant_credits`.

---

## 9. Testing (TDD, no live Stripe)

- `packs.get_pack` returns the right pack / None.
- `stripe_gateway.is_enabled()` reflects the env (set/unset `STRIPE_SECRET_KEY`).
- `service.fulfill_session`: grants exactly `credits` once; **calling it again with the same
  session_id is a no-op (no double credit)** — the key idempotency test, and the DB UNIQUE blocks a
  duplicate `StripePayment`.
- Webhook handler (gateway `construct_event` monkeypatched to return a crafted
  `checkout.session.completed` event): credits the right buyer; a bad signature (gateway raises) ⇒
  400; a replayed event ⇒ balance unchanged.
- Checkout route: disabled mode ⇒ redirect with notice; enabled mode (gateway monkeypatched) ⇒ 303
  to the session URL + a pending `StripePayment` row.
- Billing page renders the packs (and the disabled notice when off).

All tests monkeypatch `app.billing.stripe_gateway` — **no network, no Stripe account**; the full
suite stays green today.

---

## 10. Explicitly deferred (named)

Subscriptions/recurring plans + recurring webhooks; pre-created Stripe Price/Product objects;
refunds, proration, plan upgrades/downgrades; Stripe Customer objects; invoices (Stripe emails its
own receipts); DB-editable packs + admin pricing UI; multi-currency selection; tax/VAT handling.

---

## 11. Acceptance criteria

1. With `STRIPE_SECRET_KEY` unset, the app runs, the Billing page shows the disabled notice, and the
   full test suite passes (no Stripe account needed).
2. `fulfill_session` grants credits once and is idempotent on replay; the DB rejects a duplicate
   `session_id`.
3. The webhook credits the correct buyer from a verified `checkout.session.completed` event, rejects
   a bad signature with 400, and never double-credits.
4. The checkout route (gateway mocked) creates a pending `StripePayment` and redirects to the Stripe
   session URL; buyer-auth is enforced.
5. Credits are never granted by the success redirect — only by the webhook.
6. Marketplace core and `app/core/` remain free of any vertical/source strings (grep stays clean).
