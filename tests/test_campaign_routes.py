"""Task 4 tests: campaign selector UI + routes + audit (TDD — write first, run red, then implement)."""
from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient
from sqlmodel import Session, select

import app.leadvault as lv
from app.core.db import AuditLog, Segment


def _client():
    return TestClient(lv.app)


def _token_from(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


def _login(c: TestClient) -> str:
    """Log in as the demo buyer; returns the CSRF token (persists for the session)."""
    page = c.get("/login").text
    token = _token_from(page)
    c.post(
        "/login",
        data={"email": "buyer@demo.local", "password": "buyer12345", "csrf_token": token},
        follow_redirects=False,
    )
    return token


# ── (a) GET /app/campaigns → 200, both campaign names present ──────────────

def test_campaigns_page_lists_both_campaigns():
    c = _client()
    _login(c)
    r = c.get("/app/campaigns")
    assert r.status_code == 200
    assert "Utilities (UK)" in r.text
    assert "Business Restructuring" in r.text


# ── (b) POST /app/composer/apply-campaign → composition + quality key ──────

def test_apply_campaign_utilities_uk():
    c = _client()
    token = _login(c)
    r = c.post(
        "/app/composer/apply-campaign",
        json={"key": "utilities_uk", "params": {"area": "Oxford"}},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    composition = data["composition"]
    geo_nodes = [n for n in composition["nodes"] if n["predicate"] == "geo.city"]
    assert geo_nodes, "expected a geo.city node in the composition"
    assert geo_nodes[0]["params"]["value"] == "Oxford"
    assert data["quality_profile_key"] == "utilities"
    assert data["gated_notices"] == []


# ── (c) audit row campaign.select exists after apply-campaign ───────────────

def test_apply_campaign_creates_audit_row():
    c = _client()
    token = _login(c)
    c.post(
        "/app/composer/apply-campaign",
        json={"key": "utilities_uk", "params": {"area": "Oxford"}},
        headers={"X-CSRF-Token": token},
    )
    with Session(lv.engine) as s:
        rows = s.exec(
            select(AuditLog).where(AuditLog.action == "campaign.select")
        ).all()
    assert rows, "expected at least one audit row with action='campaign.select'"


# ── (d) POST /app/composer/save with origin_key persists Segment ───────────

def test_composer_save_persists_origin_key():
    c = _client()
    token = _login(c)
    composition = json.dumps({"op": "AND", "nodes": []})
    r = c.post(
        "/app/composer/save",
        data={
            "csrf_token": token,
            "name": "Utilities Oxford",
            "composition": composition,
            "origin_key": "utilities_uk",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), f"expected redirect, got {r.status_code}"
    with Session(lv.engine) as s:
        segs = s.exec(
            select(Segment).where(Segment.origin_key == "utilities_uk")
        ).all()
    assert segs, "expected a Segment with origin_key='utilities_uk'"
    assert segs[-1].origin_key == "utilities_uk"
