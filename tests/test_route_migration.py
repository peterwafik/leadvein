"""Old bookmarks must land somewhere sensible — never 404 mid-session."""
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


def _assert_redirect(c, path, expect_prefix, method="get", token=""):
    if method == "get":
        r = c.get(path, follow_redirects=False)
    else:
        r = c.post(path, data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code in (301, 302, 303, 307, 308), f"{path} -> {r.status_code}"
    assert r.headers["location"].startswith(expect_prefix), \
        f"{path} -> {r.headers['location']}"


def test_all_old_routes_redirect():
    c = _client(); token = _login(c)
    _assert_redirect(c, "/app/marketplace", "/app/find")
    _assert_redirect(c, "/app/campaigns", "/app/find")
    _assert_redirect(c, "/app/campaign-preview", "/app/find")
    _assert_redirect(c, "/app/composer", "/app/find")
    _assert_redirect(c, "/app/recipes", "/app/audiences")
    _assert_redirect(c, "/app/segments", "/app/audiences")
    _assert_redirect(c, "/app/marketplace/search", "/app/find", method="post", token=token)


def test_composer_redirect_carries_params():
    c = _client(); _login(c)
    r = c.get("/app/composer?campaign=utilities_uk", follow_redirects=False)
    assert "campaign=utilities_uk" in r.headers["location"]
    r = c.get("/app/composer?segment=7", follow_redirects=False)
    assert "audience=7" in r.headers["location"]


def test_json_endpoints_still_alive():
    c = _client(); token = _login(c)
    r = c.post("/app/composer/estimate",
               json={"composition": {"op": "AND", "nodes": []}})
    assert r.status_code == 200
    r = c.post("/app/composer/apply-campaign",
               json={"key": "utilities_uk", "params": {"area": "Oxford"}},
               headers={"X-CSRF-Token": token})
    assert r.status_code == 200


def test_nav_has_no_old_tabs():
    c = _client(); _login(c)
    html = c.get("/app/find").text
    assert 'href="/app/marketplace"' not in html
    assert 'href="/app/composer"' not in html
    assert 'href="/app/campaigns"' not in html
    assert 'href="/app/find"' in html
    assert 'href="/app/audiences"' in html
