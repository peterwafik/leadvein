from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import Response
from sqlmodel import Session, select

from app.core.compliance import audit
from app.core.db import (BuyerAccount, Lead, LeadCategoryLink, LeadRecipe, PurchasedLead,
                         SuppressionList, SuppressionEntry, CreditTransaction, _now)
from app.core.export_leads import export_purchased_csv
from app.core.marketplace import search, estimate
from app.core.masking import unlock_view, assert_owned
from app.core.purchasing import (unlock_lead, balance, InsufficientCredits,
                                 LeadSuppressed, ComplianceNotAcknowledged)
from app.core.recipes import DEFAULT_FILTERS
from app.core.targeting.segments import (create_segment, list_segments,
                                         get_owned, delete_segment)
from app.web.csrf import ensure_csrf, csrf_protect, csrf_protect_json
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


def _inventory_options(session: Session) -> dict:
    """Data-driven filter options: the cities and categories that ACTUALLY exist in
    inventory. Grows automatically as more is ingested — never a hardcoded list."""
    cities = [c for c in session.exec(
        select(Lead.city).where(Lead.city != "").distinct()).all() if c]
    cats = [c for c in session.exec(
        select(LeadCategoryLink.category_key).distinct()).all() if c]
    return {"cities": sorted(set(cities)), "cat_options": sorted(set(cats))}


@router.get("/marketplace")
def marketplace_page(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    return templates.TemplateResponse(request, "marketplace.html", {
        "request": request, "user": u, "results": None, "csrf": ensure_csrf(request),
        **_inventory_options(session)})


@router.get("/campaigns")
def campaigns_page(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    from app.campaigns.crud import list_active
    campaigns = list_active(session)
    return templates.TemplateResponse(request, "campaigns.html", {
        "request": request, "user": u, "campaigns": campaigns,
        "csrf": ensure_csrf(request)})


@router.get("/campaign-preview")
def campaign_preview(request: Request, session: Session = Depends(get_session)):
    # DESIGN PREVIEW ONLY — the Campaign layer + Targeting v2 predicate catalog are
    # approved specs, not yet built. This route renders a static click-through of the
    # TARGET UX so it can be reacted to; it wires to no engine.
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    return templates.TemplateResponse(request, "campaign_preview.html", {
        "request": request, "user": u, "csrf": ensure_csrf(request)})


@router.post("/marketplace/search", dependencies=[Depends(csrf_protect)])
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
        "filters": filters, "credits": balance(session, u.buyer_account_id),
        "csrf": ensure_csrf(request), **_inventory_options(session)})


@router.post("/unlock/{lead_id}", dependencies=[Depends(csrf_protect)])
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
    return templates.TemplateResponse(request, "compliance_ack.html", {
        "request": request, "user": u, "csrf": ensure_csrf(request)})


@router.post("/ack", dependencies=[Depends(csrf_protect)])
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
        "request": request, "user": u, "recipes": recs, "csrf": ensure_csrf(request)})


@router.post("/recipes", dependencies=[Depends(csrf_protect)])
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
        "status": request.query_params.get("status", ""),
        "csrf": ensure_csrf(request)})


@router.get("/composer")
def composer_page(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    from app.core.targeting.composer import predicate_options
    from app.fingerprints import library as fp_library
    ctx: dict = {
        "request": request, "user": u, "csrf": ensure_csrf(request),
        "options": predicate_options(session), "credits": balance(session, u.buyer_account_id),
        "tech_recipes": fp_library.list_recipes(session),
        **_inventory_options(session),
    }
    segment_id = request.query_params.get("segment")
    if segment_id:
        try:
            seg = get_owned(session, int(segment_id), u.buyer_account_id)
            if seg:
                ctx["preset"] = seg.composition_json
        except (ValueError, TypeError):
            pass
    campaign_key = request.query_params.get("campaign")
    if campaign_key:
        from app.campaigns.crud import get_by_key as get_campaign_by_key
        campaign = get_campaign_by_key(session, campaign_key)
        if campaign:
            ctx["campaign"] = campaign
            ctx["campaign_param_schema"] = json.loads(campaign.param_schema)
            audit(session, u.id, "campaign.select", "Campaign", campaign_key,
                  {"key": campaign_key, "phase": "page_load"})
    return templates.TemplateResponse(request, "composer.html", ctx)


@router.post("/composer/save", dependencies=[Depends(csrf_protect)])
async def composer_save(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    form = await request.form()
    name = form.get("name", "").strip() or "Untitled segment"
    composition_raw = form.get("composition", "{}")
    origin_key = form.get("origin_key", "") or ""
    try:
        composition = json.loads(composition_raw)
    except (json.JSONDecodeError, TypeError):
        composition = {"op": "AND", "nodes": []}
    create_segment(session, u.buyer_account_id, name, composition, origin_key=origin_key)
    return redirect("/app/segments")


@router.get("/segments")
def segments_page(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    segs = list_segments(session, u.buyer_account_id)
    return templates.TemplateResponse(request, "segments.html", {
        "request": request, "user": u, "segments": segs,
        "csrf": ensure_csrf(request)})


@router.post("/segments/{segment_id}/delete", dependencies=[Depends(csrf_protect)])
def segment_delete(request: Request, segment_id: int,
                   session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return redirect("/login")
    delete_segment(session, segment_id, u.buyer_account_id)
    return redirect("/app/segments")


@router.post("/composer/apply-campaign", dependencies=[Depends(csrf_protect_json)])
async def composer_apply_campaign(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return Response(status_code=401)
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=400)
    key = body.get("key", "")
    params = body.get("params") or {}
    from app.campaigns.crud import get_by_key as get_campaign_by_key
    campaign = get_campaign_by_key(session, key)
    if not campaign:
        return Response(status_code=404)
    from app.campaigns.compile import compile_campaign
    result = compile_campaign(campaign, params)
    # Audit with campaign key + composition hash for traceability
    import hashlib
    comp_hash = hashlib.sha256(
        json.dumps(result["composition"], sort_keys=True).encode()
    ).hexdigest()[:16]
    audit(session, u.id, "campaign.select", "Campaign", key,
          {"key": key, "composition_hash": comp_hash})
    from fastapi.responses import JSONResponse
    return JSONResponse({
        "composition": result["composition"],
        "quality_profile_key": result["quality_profile_key"],
        "gated_notices": result["gated_notices"],
    })


@router.post("/composer/estimate")
async def composer_estimate(request: Request, session: Session = Depends(get_session)):
    u = _buyer(request, session)
    if not u:
        return Response(status_code=401)
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=400)
    composition = body.get("composition") or {"op": "AND", "nodes": []}
    quality_profile_key = body.get("quality_profile_key", "") or ""
    ctx = None
    if quality_profile_key:
        try:
            from app.quality.profiles.registry import get as get_quality_profile
            prof = get_quality_profile(quality_profile_key)
            ctx = {"quality_profile": prof}
        except KeyError:
            pass  # Unknown key → baseline only, never 500
    # Audit campaign.search when estimate is driven by a campaign-derived segment
    segment_id = body.get("segment_id")
    if segment_id:
        try:
            seg = get_owned(session, int(segment_id), u.buyer_account_id)
            if seg and seg.origin_key:
                audit(session, u.id, "campaign.search", "Segment", str(seg.id),
                      {"origin_key": seg.origin_key})
        except (ValueError, TypeError):
            pass
    from app.core.targeting.estimate import estimate as targeting_estimate
    try:
        est = targeting_estimate(session, u.buyer_account_id, composition,
                                 sample=int(body.get("sample", 9)), ctx=ctx)
    except (ValueError, KeyError, TypeError):
        return Response(status_code=400)
    return est


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
        "request": request, "user": u, "entries": entries, "csrf": ensure_csrf(request)})


@router.post("/suppression", dependencies=[Depends(csrf_protect)])
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
