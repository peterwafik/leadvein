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
    return templates.TemplateResponse(request, "dashboard.html", {
        "request": request, "user": u, "credits": ba.credits,
        "n_purchased": n_purchased, "n_recipes": n_recipes,
        "acked": bool(ba.compliance_ack_at)})


@router.get("/marketplace")
def marketplace_page(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    return templates.TemplateResponse(request, "marketplace.html", {
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
    return templates.TemplateResponse(request, "marketplace.html", {
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
    except (InsufficientCredits, LeadSuppressed, ValueError):
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
    return templates.TemplateResponse(request, "purchased.html", {
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
    return templates.TemplateResponse(request, "lead_detail.html", {
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
    return templates.TemplateResponse(request, "compliance_ack.html", {"request": request, "user": u})


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
    return templates.TemplateResponse(request, "recipes.html", {
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
    return templates.TemplateResponse(request, "suppression.html", {
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
