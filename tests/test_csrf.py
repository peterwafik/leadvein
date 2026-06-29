import re
from fastapi.testclient import TestClient
import app.leadvault as lv


def _client():
    return TestClient(lv.app)


def _token_from(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


def test_login_form_has_csrf_and_rejects_missing_token():
    c = _client()
    page = c.get("/login").text
    assert _token_from(page)  # login form carries a csrf token
    # POST without the token is rejected
    r = c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345"},
               follow_redirects=False)
    assert r.status_code == 403


def test_state_change_requires_valid_csrf():
    c = _client()
    # establish a session + grab a token from a rendered form
    page = c.get("/login").text
    token = _token_from(page)
    # wrong token -> 403
    bad = c.post("/login", data={"email": "buyer@demo.local",
                 "password": "buyer12345", "csrf_token": "wrong"},
                 follow_redirects=False)
    assert bad.status_code == 403
    # correct token -> login proceeds (303 redirect)
    ok = c.post("/login", data={"email": "buyer@demo.local",
                "password": "buyer12345", "csrf_token": token},
                follow_redirects=False)
    assert ok.status_code in (302, 303)


def test_webhook_is_csrf_exempt(monkeypatch):
    from app.billing import stripe_gateway
    monkeypatch.setattr(stripe_gateway, "construct_event",
                        lambda p, s: {"type": "ignored.event", "data": {"object": {}}})
    r = _client().post("/stripe/webhook", content=b"{}",
                       headers={"Stripe-Signature": "x"})
    assert r.status_code == 200  # no CSRF needed; signature is the auth
