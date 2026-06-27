from fastapi.testclient import TestClient

import app.main as main


def client():
    return TestClient(main.app)


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
