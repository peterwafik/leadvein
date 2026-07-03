from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient
from sqlmodel import Session

import app.leadvault as lv
from app.core.db import LeadRecipe


def _client():
    return TestClient(lv.app)


def _login(c):
    m = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text)
    token = m.group(1)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": token}, follow_redirects=False)
    return token


def test_audiences_lists_segments_and_legacy_recipes():
    c = _client(); token = _login(c)
    c.post("/app/find/save", data={"csrf_token": token, "name": "Aud One",
                                   "composition": json.dumps({"op": "AND", "nodes": []}),
                                   "origin_key": ""}, follow_redirects=False)
    with Session(lv.engine) as s:
        from app.core.db import BuyerAccount, User
        from sqlmodel import select
        u = s.exec(select(User).where(User.email == "buyer@demo.local")).first()
        s.add(LeadRecipe(buyer_account_id=u.buyer_account_id, name="Old Recipe",
                         filters_json="{}", scoring_profile_key=""))
        s.commit()
    html = c.get("/app/audiences").text
    assert "Aud One" in html
    assert "Old Recipe" in html
    assert "/app/find?audience=" in html


def test_audience_delete_owned_only():
    c = _client(); token = _login(c)
    c.post("/app/find/save", data={"csrf_token": token, "name": "Aud Two",
                                   "composition": json.dumps({"op": "AND", "nodes": []}),
                                   "origin_key": ""}, follow_redirects=False)
    html = c.get("/app/audiences").text
    m = re.search(r'/app/audiences/(\d+)/delete', html)
    assert m
    r = c.post(f"/app/audiences/{m.group(1)}/delete", data={"csrf_token": token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "Aud Two" not in c.get("/app/audiences").text


def test_audience_delete_rejects_cross_account():
    # buyer A saves a segment
    ca = _client(); token_a = _login(ca)
    ca.post("/app/find/save", data={"csrf_token": token_a, "name": "Aud Secret",
                                   "composition": json.dumps({"op": "AND", "nodes": []}),
                                   "origin_key": ""}, follow_redirects=False)

    # resolve A's new segment id directly from the DB
    with Session(lv.engine) as s:
        from app.core.db import BuyerAccount, User, Segment
        from app.core.auth import create_user as _cu
        from sqlmodel import select
        u_a = s.exec(select(User).where(User.email == "buyer@demo.local")).first()
        seg = s.exec(select(Segment).where(
            Segment.buyer_account_id == u_a.buyer_account_id,
            Segment.name == "Aud Secret").order_by(Segment.id.desc())).first()
        assert seg, "buyer A segment should exist in DB"
        seg_id = seg.id

        # create buyer B — idempotent, skips if already present from a prior run
        if not s.exec(select(User).where(User.email == "buyerb_cross@demo.local")).first():
            ba_b = BuyerAccount(company_name="B Corp", credits=0)
            s.add(ba_b); s.commit(); s.refresh(ba_b)
            _cu(s, "buyerb_cross@demo.local", "buyerb12345", buyer_account_id=ba_b.id)

    # buyer B logs in on a fresh client (separate cookie jar = separate session)
    cb = _client()
    mb = re.search(r'name="csrf_token" value="([^"]+)"', cb.get("/login").text)
    token_b = mb.group(1)
    cb.post("/login", data={"email": "buyerb_cross@demo.local", "password": "buyerb12345",
                            "csrf_token": token_b}, follow_redirects=False)

    # buyer B attempts to delete buyer A's segment — ownership guard must block it silently
    r = cb.post(f"/app/audiences/{seg_id}/delete", data={"csrf_token": token_b},
                follow_redirects=False)
    assert r.status_code in (302, 303)

    # segment must still exist for buyer A (get_owned's buyer_account_id scoping exercised)
    assert "Aud Secret" in ca.get("/app/audiences").text
