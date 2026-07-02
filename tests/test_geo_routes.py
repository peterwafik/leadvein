from __future__ import annotations

import re

from fastapi.testclient import TestClient
from sqlmodel import Session, select

import app.leadvault as lv
from app.core.db import IngestRequest


def _client():
    return TestClient(lv.app)


def _token_from(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


def _login(c):
    token = _token_from(c.get("/login").text)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": token}, follow_redirects=False)
    return token


def test_countries_endpoint_lists_all_with_honest_counts():
    c = _client(); _login(c)
    r = c.get("/app/geo/countries")
    assert r.status_code == 200
    by_code = {x["code"]: x for x in r.json()["countries"]}
    assert "FR" in by_code                       # complete: even with 0 leads
    assert by_code["FR"]["lead_count"] == 0      # honest zero, never faked


def test_areas_endpoint_groups_and_counts():
    c = _client(); _login(c)
    r = c.get("/app/geo/areas", params={"country": "GB", "q": "oxford"})
    assert r.status_code == 200
    data = r.json()
    all_areas = [a for g in data["groups"] for a in g["areas"]]
    ox = next(a for a in all_areas if a["name"] == "Oxford")
    assert isinstance(ox["lead_count"], int)     # 0 is fine — must be present + honest
    labels = [g["label"] for g in data["groups"]]
    assert any("Oxfordshire" in l for l in labels)


def test_areas_requires_auth():
    c = _client()
    r = c.get("/app/geo/areas", params={"country": "GB"}, follow_redirects=False)
    assert r.status_code in (302, 303, 401)


def test_ingest_request_created_and_deduped():
    c = _client(); token = _login(c)
    for _ in range(2):
        r = c.post("/app/geo/ingest-request",
                   json={"country": "GB", "area": "Bicester"},
                   headers={"X-CSRF-Token": token})
        assert r.status_code == 200
    with Session(lv.engine) as s:
        rows = s.exec(select(IngestRequest).where(
            IngestRequest.area == "Bicester", IngestRequest.status == "open")).all()
    assert len(rows) == 1
