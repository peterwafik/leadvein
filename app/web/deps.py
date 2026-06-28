from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.core.auth import get_user

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# the engine is created in app.leadvault and injected at import time
_engine = None


def set_engine(engine) -> None:
    global _engine
    _engine = engine


def get_session():
    with Session(_engine) as s:
        yield s


def login_user(request: Request, user) -> None:
    request.session["user_id"] = user.id


def logout_user(request: Request) -> None:
    request.session.pop("user_id", None)


def current_user(request: Request, session: Session):
    uid = request.session.get("user_id")
    return get_user(session, uid) if uid else None


def require_buyer(request: Request, session: Session):
    u = current_user(request, session)
    if not u:
        return None
    return u


def require_admin(request: Request, session: Session):
    u = current_user(request, session)
    if u and u.role == "admin":
        return u
    return None


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)
