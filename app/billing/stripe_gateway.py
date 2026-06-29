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
