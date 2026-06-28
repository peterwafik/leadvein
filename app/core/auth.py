from __future__ import annotations

from passlib.context import CryptContext
from sqlmodel import Session, select

from app.core.db import User

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(p: str) -> str:
    return _pwd.hash(p)


def verify_password(p: str, h: str) -> bool:
    try:
        return _pwd.verify(p, h)
    except Exception:
        return False


def create_user(session: Session, email: str, password: str, role: str = "buyer",
                buyer_account_id: int | None = None) -> User:
    u = User(email=email.strip().lower(), password_hash=hash_password(password),
             role=role, buyer_account_id=buyer_account_id)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def authenticate(session: Session, email: str, password: str) -> User | None:
    u = session.exec(select(User).where(User.email == email.strip().lower())).first()
    if u and verify_password(password, u.password_hash):
        return u
    return None


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)
