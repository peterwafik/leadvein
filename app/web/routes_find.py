from __future__ import annotations

import hashlib
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


def _tech_groups(recipes) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for r in recipes:
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
    from app.fingerprints.library import list_recipes
    recipes = list_recipes(session)
    counts = geo_lead_counts(session)["countries"]
    ctx: dict = {
        "request": request, "user": u, "csrf": ensure_csrf(request),
        "credits": balance(session, u.buyer_account_id),
        "campaigns": list_active(session),
        "countries": [{"code": c.country_code, "name": c.country_name,
                       "lead_count": counts.get(c.country_code, 0)}
                      for c in list_countries(session)],
        "cat_options": _category_counts(session),
        "tech_groups": _tech_groups(recipes),
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
    ctx["tech_recipes"] = recipes                    # reuse the same fetch
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
        scoring_profile_key = camp.scoring_profile_key or ""
    ck = channel_profile_key(answers.get("contact_channel", ""))
    if ck and ck not in quality_keys:
        quality_keys.append(ck)

    sentence = render_sentence(session, composition, quality_profile_keys=quality_keys)
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
