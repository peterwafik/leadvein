from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

import app.core.config as config
import app.campaigns.models  # noqa — register Campaign table BEFORE init_db
from app.core.db import init_db, User, BuyerAccount
from app.core.auth import create_user
from app.seed import seed_all
from app.web import deps
from app.web.routes_admin import router as admin_router
from app.web.routes_auth import router as auth_router
from app.web.routes_buyer import router as buyer_router
from app.web.routes_billing import router as billing_router
from app.web.routes_public import router as public_router

# Operational logging: always to stderr; also to LEADVAULT_LOG file if set. Unhandled
# errors are logged with traceback (see the exception handler below) so a pilot operator
# has a persistent record to review.
import logging

_log_handlers: list[logging.Handler] = [logging.StreamHandler()]
_log_file = os.getenv("LEADVAULT_LOG")
if _log_file:
    _log_handlers.append(logging.FileHandler(_log_file))
logging.basicConfig(level=logging.INFO, handlers=_log_handlers,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("leadvault")

app = FastAPI(title="LeadVault", debug=False)
app.add_middleware(SessionMiddleware, **config.session_kwargs())


@app.exception_handler(Exception)
async def _log_unhandled(request: Request, exc: Exception):
    from fastapi.responses import PlainTextResponse
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return PlainTextResponse("Internal Server Error", status_code=500)

engine = init_db(os.getenv("LEADVAULT_DB", "sqlite:///leadvault.db"))
deps.set_engine(engine)


def _seed_accounts() -> None:
    from app.campaigns.seed import seed_campaigns
    with Session(engine) as s:
        seed_all(s)
        seed_campaigns(s)
        creds = config.admin_credentials()
        if creds is not None:
            admin_email, admin_pw = creds
            if not s.exec(select(User).where(User.email == admin_email)).first():
                create_user(s, admin_email, admin_pw, role="admin")
        else:
            print("WARNING: LEADVAULT_ADMIN_EMAIL/PASSWORD not set; no admin seeded")
        if config.seed_demo_buyer():
            if not s.exec(select(User).where(User.email == "buyer@demo.local")).first():
                ba = BuyerAccount(company_name="Demo Buyer", credits=100)
                s.add(ba); s.commit(); s.refresh(ba)
                create_user(s, "buyer@demo.local", "buyer12345", role="buyer",
                            buyer_account_id=ba.id)


_seed_accounts()

app.include_router(auth_router)
app.include_router(buyer_router)
app.include_router(admin_router)
app.include_router(billing_router)
app.include_router(public_router)

from app.targeting.runtime import register_targeting_runtime
register_targeting_runtime()

from app.quality.runtime import register_quality_runtime
register_quality_runtime()

from app.compliance.outreach_gate import register_outreach_gate
register_outreach_gate()

from app.adapters.providers import register_providers
register_providers()


@app.get("/")
def root():
    return RedirectResponse("/login", status_code=303)
