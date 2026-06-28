from fastapi.testclient import TestClient
import app.leadvault as lv


def client():
    return TestClient(lv.app)


def test_login_page_loads():
    assert client().get("/login").status_code == 200


def test_demo_buyer_login_sets_session():
    c = client()
    r = c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345"},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "session" in r.headers.get("set-cookie", "").lower()


def test_full_buyer_journey(monkeypatch):
    from sqlmodel import Session
    import json
    from app.core.db import Lead, _now
    # seed one matching lead directly into the app DB
    with Session(lv.engine) as s:
        s.add(Lead(business_name="Hidden Diner",
                   category_keys_json=json.dumps(["restaurant"]), city="London",
                   phone="+44 1", public_email="info@diner.com",
                   website_url="https://hiddendiner.co.uk", score_total=85,
                   subscores_json=json.dumps({"fit": 85}),
                   score_explanation="independent restaurant, open 7 days",
                   source_name="OpenStreetMap (Overpass)", source_url="http://osm",
                   source_license="ODbL", date_last_verified=_now(), price_credits=3))
        s.commit()
    c = client()
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345"})
    # marketplace search returns a MASKED card (no business name / contact)
    r = c.post("/app/marketplace/search",
               data={"categories": "restaurant", "city": "London", "min_score": "50"})
    assert r.status_code == 200
    assert "Hidden Diner" not in r.text and "hiddendiner.co.uk" not in r.text
    assert "85" in r.text  # score visible
    # accept compliance, then unlock
    c.post("/app/ack")
    lead_id = None
    with Session(lv.engine) as s:
        from sqlmodel import select
        lead_id = s.exec(select(Lead).where(Lead.business_name == "Hidden Diner")).first().id
    ru = c.post(f"/app/unlock/{lead_id}", follow_redirects=False)
    assert ru.status_code in (302, 303)
    # purchased detail now shows full contact
    detail = c.get(f"/app/purchased/{lead_id}")
    assert detail.status_code == 200
    assert "Hidden Diner" in detail.text and "info@diner.com" in detail.text
    # export contains the unlocked contact
    ex = c.get("/app/export.csv")
    assert ex.status_code == 200 and "info@diner.com" in ex.text
    # a different buyer cannot view the detail (ownership guard)
