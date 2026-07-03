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
