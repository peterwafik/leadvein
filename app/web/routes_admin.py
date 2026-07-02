from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Form
from sqlmodel import Session, select

from app.adapters import registry as adapter_registry
from app.adapters.base import AdapterQuery
from app.core.compliance import audit, lead_opted_out
from app.core.retention import purge_expired, expired_count
from app.core.db import (Lead, LeadSource, AuditLog, OptOutRequest, IngestionJob,
                         BuyerAccount)
from app.core.taxonomy import all_categories, upsert_category
from app.core.purchasing import grant_credits
from app.enrich.website import enrich_website
from app.ingestion.pipeline import ingest
from app.web.csrf import ensure_csrf, csrf_protect
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
    n_expired = expired_count(session)
    return templates.TemplateResponse(request, "admin_overview.html", {
        "request": request, "user": u, "n_leads": n_leads, "n_sources": n_sources,
        "n_expired": n_expired, "csrf": ensure_csrf(request)})


@router.post("/recompute-coverage", dependencies=[Depends(csrf_protect)])
def recompute_coverage_route(request: Request, session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    from app.core.targeting.coverage import recompute_coverage
    n = recompute_coverage(session)
    audit(session, u.id, "recompute_coverage", "AttributeCoverage", "*", {"paths": n})
    return redirect("/admin")


@router.post("/purge-expired", dependencies=[Depends(csrf_protect)])
def purge_expired_route(request: Request, session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    from app.core.compliance import audit
    n = purge_expired(session)
    audit(session, u.id, "purge_expired", "Lead", "*", {"removed": n})
    return redirect("/admin")


@router.get("/ingest")
def ingest_page(request: Request, session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    return templates.TemplateResponse(request, "admin_ingest.html", {
        "request": request, "user": u, "adapters": adapter_registry.all_keys(),
        "result": None, "csrf": ensure_csrf(request)})


@router.post("/ingest", dependencies=[Depends(csrf_protect)])
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
    return templates.TemplateResponse(request, "admin_ingest.html", {
        "request": request, "user": u, "adapters": adapter_registry.all_keys(),
        "result": counts, "csrf": ensure_csrf(request)})


@router.get("/leads")
def leads(request: Request, session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    leads = session.exec(select(Lead).order_by(Lead.id.desc())).all()[:200]
    rows = [{"lead": l, "opted_out": lead_opted_out(session, l)} for l in leads]
    return templates.TemplateResponse(request, "admin_leads.html", {
        "request": request, "user": u, "rows": rows})


@router.get("/sources")
def sources(request: Request, session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    rows = session.exec(select(LeadSource)).all()
    return templates.TemplateResponse(request, "admin_sources.html", {
        "request": request, "user": u, "rows": rows})


@router.get("/categories")
def categories(request: Request, session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    return templates.TemplateResponse(request, "admin_categories.html", {
        "request": request, "user": u, "cats": all_categories(session),
        "csrf": ensure_csrf(request)})


@router.post("/categories", dependencies=[Depends(csrf_protect)])
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
    return templates.TemplateResponse(request, "admin_optouts.html", {
        "request": request, "user": u, "rows": rows, "csrf": ensure_csrf(request)})


@router.post("/optouts", dependencies=[Depends(csrf_protect)])
def optouts_add(request: Request, kind: str = Form(...), value: str = Form(...),
                session: Session = Depends(get_session)):
    u = _admin(request, session)
    if not u:
        return redirect("/login")
    session.add(OptOutRequest(kind=kind, value=value.strip().lower(), applied=True))
    session.commit()
    audit(session, u.id, "optout_add", "OptOutRequest", value, {"kind": kind})
    return redirect("/admin/optouts")


@router.post("/grant", dependencies=[Depends(csrf_protect)])
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
    return templates.TemplateResponse(request, "admin_audit.html", {
        "request": request, "user": u, "rows": rows})
