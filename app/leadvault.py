from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

from app.core.db import init_db, User, BuyerAccount
from app.core.auth import create_user
from app.seed import seed_all
from app.web import deps
from app.web.routes_auth import router as auth_router
from app.web.routes_buyer import router as buyer_router

app = FastAPI(title="LeadVault")
app.add_middleware(SessionMiddleware,
                   secret_key=os.getenv("LEADVAULT_SECRET", "dev-leadvault-secret"))

engine = init_db("sqlite:///leadvault.db")
deps.set_engine(engine)


def _seed_accounts() -> None:
    with Session(engine) as s:
        seed_all(s)
        if not s.exec(select(User).where(User.role == "admin")).first():
            create_user(s, "admin@leadvault.local",
                        os.getenv("LEADVAULT_ADMIN_PW", "admin12345"), role="admin")
        if not s.exec(select(User).where(User.email == "buyer@demo.local")).first():
            ba = BuyerAccount(company_name="Demo Buyer", credits=100)
            s.add(ba); s.commit(); s.refresh(ba)
            create_user(s, "buyer@demo.local", "buyer12345", role="buyer",
                        buyer_account_id=ba.id)


_seed_accounts()

app.include_router(auth_router)
app.include_router(buyer_router)


@app.get("/")
def root():
    return RedirectResponse("/login", status_code=303)
