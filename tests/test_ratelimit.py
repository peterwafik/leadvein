from app.web.ratelimit import check, reset


def test_blocks_after_limit():
    reset()
    for _ in range(5):
        assert check("k", 5, 60, now=100.0) is True
    assert check("k", 5, 60, now=100.0) is False   # 6th in-window is blocked


def test_window_expiry_allows_again():
    reset()
    assert check("w", 2, 10, now=100.0) is True
    assert check("w", 2, 10, now=100.0) is True
    assert check("w", 2, 10, now=100.0) is False    # limit hit
    assert check("w", 2, 10, now=111.0) is True      # window passed -> allowed


def test_keys_are_independent():
    reset()
    assert check("a", 1, 60, now=1.0) is True
    assert check("a", 1, 60, now=1.0) is False
    assert check("b", 1, 60, now=1.0) is True        # different key unaffected


def test_login_returns_429_after_too_many_attempts():
    from fastapi.testclient import TestClient
    import app.leadvault as lv
    import re
    reset()
    c = TestClient(lv.app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    codes = []
    for _ in range(12):
        r = c.post("/login", data={"email": "x@y.com", "password": "nope",
                   "csrf_token": token}, follow_redirects=False)
        codes.append(r.status_code)
    assert 429 in codes          # the limiter kicks in within 12 attempts (limit 10/60s)
