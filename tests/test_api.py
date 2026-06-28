import base64

from fastapi.testclient import TestClient

import app.main as main


def client():
    return TestClient(main.app)


def _basic(user, pw):
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


CUSTOM_BODY = {"category": "Custom", "type": "AuthTest",
               "urlscan_query": "domain:x.com", "verify_fingerprints": ["x.com"]}


def test_recipe_management_open_when_no_admin_password(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    c = client()
    r = c.post("/api/recipes", json=CUSTOM_BODY)
    assert r.status_code == 200  # open/local mode — no auth required


def test_recipe_management_locked_when_admin_password_set(monkeypatch):
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    c = client()
    # no credentials -> 401
    assert c.post("/api/recipes", json=CUSTOM_BODY).status_code == 401
    # wrong credentials -> 401
    bad = {"Authorization": _basic("admin", "nope")}
    assert c.post("/api/recipes", json=CUSTOM_BODY, headers=bad).status_code == 401
    # correct credentials -> 200
    ok = {"Authorization": _basic("admin", "s3cret")}
    assert c.post("/api/recipes", json=CUSTOM_BODY, headers=ok).status_code == 200
    # recipe/test is gated the same way
    assert c.post("/api/recipes/test", json={"urlscan_query": "domain:x.com",
                  "verify_fingerprints": ["x.com"]}).status_code == 401


def test_jobs_are_run_only_not_admin_gated(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    main.FETCH_OVERRIDE = lambda url, **k: (url, "<html><title>x</title></html>")
    try:
        c = client()
        # running a job needs NO admin auth even when auth is enabled
        r = c.post("/api/jobs", json={"recipe_id": "gloriafood",
                   "manual_hosts": ["x.com"], "delay": 0.0})
        assert r.status_code == 200
        # listing recipes also stays open
        assert c.get("/api/recipes").status_code == 200
    finally:
        main.FETCH_OVERRIDE = None


def test_recipes_endpoint_lists_builtins():
    c = client()
    r = c.get("/api/recipes")
    assert r.status_code == 200
    data = r.json()
    ids = [x["id"] for x in data["recipes"]]
    assert "gloriafood" in ids
    assert "Online Ordering / Restaurants" in data["grouped"]


def test_create_custom_recipe():
    c = client()
    body = {"category": "Custom", "type": "Calendly Custom",
            "urlscan_query": "domain:assets.calendly.com",
            "verify_fingerprints": ["assets.calendly.com"]}
    r = c.post("/api/recipes", json=body)
    assert r.status_code == 200
    assert r.json()["type"] == "Calendly Custom"


def test_index_served():
    c = client()
    r = c.get("/")
    assert r.status_code == 200
    assert "Lead Scraper" in r.text


def test_job_run_with_manual_hosts():
    # manual_hosts bypasses discovery; FETCH_OVERRIDE avoids the network entirely.
    def fake_fetch(url, **kwargs):
        return url, ('<html><title>Mario</title><body>'
                     '<script src="https://fbgcdn.com/embedder/js/ewm2.js"></script>'
                     '<a href="mailto:info@marios.com">e</a></body></html>')

    main.FETCH_OVERRIDE = fake_fetch
    try:
        c = client()
        rj = c.post("/api/jobs", json={"recipe_id": "gloriafood",
                                       "manual_hosts": ["marios.com"],
                                       "delay": 0.0, "only_confirmed": True})
        job_id = rj.json()["job_id"]
        with c.stream("GET", f"/api/jobs/{job_id}/stream") as resp:
            body = "".join(chunk for chunk in resp.iter_text())
        assert "done" in body
        assert "(manual domain list)" in body  # query surfaced
        rx = c.get(f"/api/jobs/{job_id}/results.csv")
        assert rx.status_code == 200
        assert "marios.com" in rx.text
    finally:
        main.FETCH_OVERRIDE = None


def test_recipe_test_survives_enrich_error(monkeypatch):
    monkeypatch.setattr(main, "discover", lambda recipe, **k: ["x.com"])
    def boom(url, **kwargs):
        raise RuntimeError("net down")
    main.FETCH_OVERRIDE = boom
    try:
        c = client()
        r = c.post("/api/recipes/test", json={"urlscan_query": "domain:x.com",
                   "verify_fingerprints": ["x.com"], "source": "urlscan"})
        assert r.status_code == 200
        data = r.json()
        assert data["checked"] == 1
        assert data["matched"] == 0
    finally:
        main.FETCH_OVERRIDE = None


def test_restream_completed_job_returns_409():
    def fake_fetch(url, **kwargs):
        return url, "<html><title>x</title></html>"
    main.FETCH_OVERRIDE = fake_fetch
    try:
        c = client()
        job_id = c.post("/api/jobs", json={"recipe_id": "gloriafood",
                        "manual_hosts": ["marios.com"], "delay": 0.0,
                        "only_confirmed": False}).json()["job_id"]
        with c.stream("GET", f"/api/jobs/{job_id}/stream") as resp:
            "".join(resp.iter_text())
        r2 = c.get(f"/api/jobs/{job_id}/stream")
        assert r2.status_code == 409
    finally:
        main.FETCH_OVERRIDE = None
