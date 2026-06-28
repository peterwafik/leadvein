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
