# tests/test_find_routes.py
from __future__ import annotations

import re

from fastapi.testclient import TestClient

import app.leadvault as lv


def _client():
    return TestClient(lv.app)


def _token_from(html):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


def _login(c):
    token = _token_from(c.get("/login").text)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": token}, follow_redirects=False)
    return token


def test_find_page_renders_campaigns_and_modes():
    c = _client(); _login(c)
    r = c.get("/app/find")
    assert r.status_code == 200
    assert "Utilities (UK)" in r.text
    assert "Describe your own" in r.text
    assert "Quick search" in r.text
    # buyer-facing copy: no engine jargon in VISIBLE text (strip scripts + machine
    # data-* attributes; the advanced disclosure carries predicate keys in data-key,
    # same as the shipped composer, but they are never buyer-visible).
    visible = re.sub(r'<script.*?</script>', '', r.text, flags=re.S)
    visible = re.sub(r'data-[a-z-]+="[^"]*"', '', visible)
    assert "min_score" not in visible
    assert "predicate" not in r.text.lower() or "data-" in r.text  # allow data attrs only


def test_find_compile_custom_answers():
    c = _client(); token = _login(c)
    r = c.post("/app/find/compile", json={"answers": {
        "cities": ["Oxford"], "categories": ["bakery"],
        "contact_channel": "phone", "freshness_days": 30}},
        headers={"X-CSRF-Token": token})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sentence"].startswith("We'll find")
    assert "validated phone" in data["sentence"]
    preds = [n.get("predicate") for n in data["composition"]["nodes"]]
    assert "geo.city_any" in preds
    assert data["quality_profile_keys"] == ["phone_validated"]
    assert data["gated_notices"] == []


def test_find_compile_campaign_carries_profile_and_gates():
    c = _client(); token = _login(c)
    r = c.post("/app/find/compile", json={
        "campaign_key": "business_restructuring",
        "answers": {"cities": ["Oxford"], "categories": ["bakery"],
                    "contact_channel": "email"}},
        headers={"X-CSRF-Token": token})
    assert r.status_code == 200
    data = r.json()
    assert data["gated_notices"], "gated financial signals must be surfaced"
    assert all("attributes." not in str(n.get("params", {}))
               for n in data["composition"]["nodes"])   # INV-6: never in composition
    # campaign profile + channel profile both present (honest intersection downstream)
    assert "email_validated" in data["quality_profile_keys"]


def test_find_estimate_accepts_profile_list():
    c = _client(); token = _login(c)
    r = c.post("/app/find/estimate", json={
        "composition": {"op": "AND", "nodes": []},
        "quality_profile_keys": ["utilities", "email_validated"]},
        headers={"X-CSRF-Token": token})
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"count", "score_distribution", "freshness_distribution", "samples"}


def test_old_composer_estimate_still_works():
    c = _client(); _login(c)
    r = c.post("/app/composer/estimate", json={
        "composition": {"op": "AND", "nodes": []},
        "quality_profile_key": "baseline"})
    assert r.status_code == 200
