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
    try:
        record_pending(session, sess["id"], u.buyer_account_id, pack.key, pack.credits,
                       pack.amount_cents, packs.currency())
    except Exception:
        return redirect("/app/billing?status=error")
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
        buyer_id = int(meta.get("buyer_account_id", 0) or 0)
        credits = int(meta.get("credits", 0) or 0)
        if buyer_id and credits:
            fulfill_session(session, obj.get("id"), buyer_id, credits,
                            meta.get("pack_key", ""),
                            int(obj.get("amount_total") or 0),
                            obj.get("currency", "gbp"))
    return Response(status_code=200)
