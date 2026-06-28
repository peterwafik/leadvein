from sqlmodel import Session
from app.core.db import init_db, BuyerAccount
from app.core.auth import (hash_password, verify_password, create_user,
                           authenticate, get_user)


def test_password_hash_roundtrip():
    h = hash_password("s3cret")
    assert h != "s3cret"
    assert verify_password("s3cret", h) is True
    assert verify_password("wrong", h) is False


def test_create_and_authenticate():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba = BuyerAccount(company_name="Acme", credits=0)
        s.add(ba); s.commit(); s.refresh(ba)
        u = create_user(s, "a@b.com", "pw", role="buyer", buyer_account_id=ba.id)
        assert u.id is not None and u.password_hash != "pw"
        assert authenticate(s, "a@b.com", "pw").id == u.id
        assert authenticate(s, "a@b.com", "bad") is None
        assert authenticate(s, "missing@b.com", "pw") is None
        assert get_user(s, u.id).email == "a@b.com"
