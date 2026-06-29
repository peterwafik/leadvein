from __future__ import annotations

import secrets

from fastapi import Request, HTTPException


def ensure_csrf(request: Request) -> str:
    """Return the session's CSRF token, generating one on first use."""
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def csrf_ok(request: Request, submitted: str) -> bool:
    token = request.session.get("csrf")
    return bool(token) and secrets.compare_digest(token, submitted or "")


async def csrf_protect(request: Request) -> None:
    """FastAPI dependency for state-changing POST routes. Reads the form within the
    route's own request context (no double-body-read). Raises 403 on mismatch."""
    form = await request.form()
    if not csrf_ok(request, form.get("csrf_token", "")):
        raise HTTPException(status_code=403, detail="CSRF token invalid")
