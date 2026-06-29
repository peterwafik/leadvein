from fastapi.testclient import TestClient

import app.leadvault as lv


@lv.app.get("/_boom_for_test")
def _boom():
    raise RuntimeError("kaboom-test")


def test_unhandled_errors_are_caught_and_logged(caplog):
    c = TestClient(lv.app, raise_server_exceptions=False)
    with caplog.at_level("ERROR", logger="leadvault"):
        r = c.get("/_boom_for_test")
    # client gets a clean 500 (no traceback leaked), and it is logged for the operator
    assert r.status_code == 500
    assert "Internal Server Error" in r.text
    assert any("unhandled error" in rec.message or "kaboom-test" in str(rec.exc_info)
               for rec in caplog.records)
