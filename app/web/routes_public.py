"""Public, no-login compliance routes. A business can opt out of LeadVault without
an account; a submitted opt-out is applied immediately and suppresses that business
across search, preview, unlock, and export (via the single OptOutRequest source)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Form
from sqlmodel import Session

from app.core.db import OptOutRequest
from app.core.compliance import audit
from app.web.deps import get_session, redirect, templates
from app.web.csrf import csrf_protect, ensure_csrf

router = APIRouter()

_KINDS = ("domain", "phone", "email")


@router.get("/opt-out")
def optout_form(request: Request):
    return templates.TemplateResponse(request, "optout.html", {
        "request": request, "csrf": ensure_csrf(request),
        "status": request.query_params.get("status", "")})


@router.post("/opt-out", dependencies=[Depends(csrf_protect)])
def optout_submit(request: Request, kind: str = Form(...), value: str = Form(...),
                  session: Session = Depends(get_session)):
    kind = (kind or "").strip().lower()
    value = (value or "").strip().lower()
    if kind in _KINDS and value:
        session.add(OptOutRequest(kind=kind, value=value, applied=True))
        session.commit()
        audit(session, None, "public_optout", "OptOutRequest", value, {"kind": kind})
        return redirect("/opt-out?status=done")
    return redirect("/opt-out?status=invalid")
