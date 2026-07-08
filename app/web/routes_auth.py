from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Form
from sqlmodel import Session

from app.core.auth import authenticate, create_user
from app.core.db import BuyerAccount
from app.web.csrf import ensure_csrf, csrf_protect
from app.web.deps import (templates, get_session, current_user, login_user,
                          logout_user, redirect)
from app.web.ratelimit import rate_limiter

router = APIRouter()


@router.get("/login")
def login_page(request: Request, session: Session = Depends(get_session)):
    u = current_user(request, session)
    if u:
        # Route by role: /app is buyer-only and bounces admins back to /login,
        # so sending a logged-in admin to /app would loop forever. Mirror the
        # POST handler, which already lands admins on /admin.
        return redirect("/admin" if u.role == "admin" else "/app")
    return templates.TemplateResponse(request, "login.html", {
        "request": request, "user": None, "csrf": ensure_csrf(request)})


@router.post("/login", dependencies=[Depends(rate_limiter(10, 60)), Depends(csrf_protect)])
def login_submit(request: Request, email: str = Form(...), password: str = Form(...),
                 session: Session = Depends(get_session)):
    user = authenticate(session, email, password)
    if not user:
        return templates.TemplateResponse(request,
            "login.html", {"request": request, "user": None,
                           "error": "Invalid credentials",
                           "csrf": ensure_csrf(request)}, status_code=401)
    login_user(request, user)
    return redirect("/admin" if user.role == "admin" else "/app")


@router.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {
        "request": request, "user": None, "csrf": ensure_csrf(request)})


@router.post("/register", dependencies=[Depends(csrf_protect)])
def register_submit(request: Request, company: str = Form(...), email: str = Form(...),
                    password: str = Form(...), session: Session = Depends(get_session)):
    from sqlmodel import select
    from app.core.db import User
    if session.exec(select(User).where(User.email == email.strip().lower())).first():
        return templates.TemplateResponse(request,
            "register.html", {"request": request, "user": None,
                              "error": "Email already registered",
                              "csrf": ensure_csrf(request)}, status_code=400)
    ba = BuyerAccount(company_name=company, credits=0)
    session.add(ba); session.commit(); session.refresh(ba)
    user = create_user(session, email, password, role="buyer", buyer_account_id=ba.id)
    login_user(request, user)
    return redirect("/app")


@router.get("/logout")
def logout(request: Request):
    logout_user(request)
    return redirect("/login")
