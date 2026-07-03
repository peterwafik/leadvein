from __future__ import annotations

import re

from fastapi.testclient import TestClient

import app.leadvault as lv


def _client():
    return TestClient(lv.app)


def _login(c):
    m = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text)
    token = m.group(1)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": token}, follow_redirects=False)
    return token


def test_find_page_has_stepper_and_steps():
    c = _client(); _login(c)
    html = c.get("/app/find").text
    for label in ("Campaign", "Where", "Who", "Quality bar", "Review"):
        assert label in html
    assert "Whole country" in html
    assert "not yet ingested" in html.lower() or "data-zero-copy" in html  # zero-state copy present


def test_find_page_verified_live_always_locked():   # INV-Q2 in the UI
    c = _client(); _login(c)
    html = c.get("/app/find").text
    assert "Verified-live" in html
    assert "requires licensed provider" in html
    m = re.search(r'<[^>]*data-tier-locked[^>]*>', html)
    assert m, "Verified-live must be a locked row (data-tier-locked), never an input"


def test_find_page_greyed_recipes_not_selectable():   # INV-13 in the UI
    c = _client(); _login(c)
    html = c.get("/app/find").text
    # disabled recipes render with data-recipe-disabled and no checkbox input
    if "data-recipe-disabled" in html:
        seg = html.split("data-recipe-disabled", 1)[1][:300]
        assert "<input" not in seg.split(">", 1)[1][:200]


def test_find_page_no_engine_jargon():
    c = _client(); _login(c)
    html = c.get("/app/find").text
    visible = re.sub(r'<script.*?</script>', '', html, flags=re.S)
    visible = re.sub(r'data-[a-z-]+="[^"]*"', '', visible)
    assert "min_score" not in visible
    assert "quality.min" not in visible
    assert "geo.city_any" not in visible


def test_quick_mode_renders():
    c = _client(); _login(c)
    r = c.get("/app/find", params={"mode": "quick"})
    assert r.status_code == 200
    assert "Quick search" in r.text
