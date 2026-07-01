from __future__ import annotations

import os

DEV_SECRET = "dev-leadvault-secret"


def env() -> str:
    return (os.getenv("LEADVAULT_ENV") or "dev").lower()


def is_prod() -> bool:
    return env() == "prod"


def secret() -> str:
    s = os.getenv("LEADVAULT_SECRET") or DEV_SECRET
    if is_prod() and s == DEV_SECRET:
        raise RuntimeError(
            "LEADVAULT_SECRET must be set to a strong, unique value in production "
            "(LEADVAULT_ENV=prod). Refusing to start with the dev default.")
    return s


def session_kwargs() -> dict:
    # SessionMiddleware sets HttpOnly automatically; https_only adds the Secure flag.
    return {"secret_key": secret(), "session_cookie": "leadvault_session",
            "https_only": is_prod(), "same_site": "lax"}


def admin_credentials() -> tuple[str, str] | None:
    """(email, password) to seed the admin. In prod, both must be provided via env
    or None is returned (caller must NOT seed a weak default)."""
    email = os.getenv("LEADVAULT_ADMIN_EMAIL")
    pw = os.getenv("LEADVAULT_ADMIN_PASSWORD")
    if is_prod():
        if email and pw:
            return email, pw
        return None
    return (email or "admin@leadvault.local", pw or "admin12345")


def seed_demo_buyer() -> bool:
    v = os.getenv("LEADVAULT_SEED_DEMO_BUYER")
    if v:  # empty string or unset -> fall through to the env default (an empty
           # .env line must NOT be read as an explicit "false")
        return v.strip().lower() in ("1", "true", "yes", "on")
    return not is_prod()  # demo buyer seeded in dev only, by default
