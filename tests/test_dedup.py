from app.adapters.base import NormalizedLead
from app.core.dedup import dedupe_key, find_existing
from app.core.db import init_db, Lead
from sqlmodel import Session


def _lead(**kw):
    base = dict(business_name="X", category_keys=[], address={})
    base.update(kw)
    return NormalizedLead(**base)


def test_dedupe_key_prefers_domain_then_phone_then_name():
    assert dedupe_key(_lead(website_url="https://www.joe.com/x")) == "domain:joe.com"
    assert dedupe_key(_lead(phone="+44 20 1234 5678")) == "phone:442012345678"
    k = dedupe_key(_lead(business_name="Joe's Diner", address={"city": "London"}))
    assert k == "name:joes-diner|london"


def test_find_existing():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        s.add(Lead(business_name="Joe", dedupe_key="domain:joe.com"))
        s.commit()
        assert find_existing(s, "domain:joe.com") is not None
        assert find_existing(s, "domain:nope.com") is None
