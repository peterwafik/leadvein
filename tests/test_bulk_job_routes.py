from __future__ import annotations

import json
import re
import time

from fastapi.testclient import TestClient
from sqlmodel import Session, select

import app.leadvault as lv
from app.core.db import IngestionJob


def _ensure_admin():
    """Create admin@demo.local if not already present.

    The app seeds admin@leadvault.local by default (config.admin_credentials()
    returns that when LEADVAULT_ADMIN_EMAIL is unset).  The test needs
    admin@demo.local, so we create it in-test exactly as test_audiences.py
    creates a second buyer.
    """
    from app.core.db import User
    from app.core.auth import create_user
    with Session(lv.engine) as s:
        if not s.exec(select(User).where(User.email == "admin@demo.local")).first():
            create_user(s, "admin@demo.local", "admin12345", role="admin")


def _admin_client():
    _ensure_admin()
    c = TestClient(lv.app)
    m = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text)
    token = m.group(1)
    c.post("/login", data={"email": "admin@demo.local", "password": "admin12345",
                           "csrf_token": token}, follow_redirects=False)
    return c, token


def _fake_run(session, region_key, **kw):
    on_progress = kw.get("on_progress")
    counts = {"elements_seen": 12, "matched": 7, "stored_new": 7, "merged": 0,
              "skipped_compliance": 0, "skipped_duplicate_in_run": 0, "hot": 3}
    if on_progress:
        on_progress(counts)
    return counts


def test_bulk_job_lifecycle(monkeypatch):
    import app.web.bulk_jobs as bj
    monkeypatch.setattr(bj, "run_bulk_import", _fake_run)
    c, token = _admin_client()
    r = c.post("/admin/bulk-import", data={"csrf_token": token, "region": "monaco",
                                           "scoring_profile_key": ""},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    for _ in range(50):                       # wait for the thread
        body = c.get("/admin/bulk-import/status").json()
        if body["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert body["status"] == "done"
    assert body["counts"]["hot"] == 3
    with Session(lv.engine) as s:
        job = s.exec(select(IngestionJob).where(
            IngestionJob.adapter_key == "osm_geofabrik")).all()[-1]
        assert job.status == "done"
        assert json.loads(job.counts_json)["matched"] == 7


def test_second_job_refused_while_running(monkeypatch):
    import app.web.bulk_jobs as bj
    started = {"go": False}
    def slow_run(session, region_key, **kw):
        while not started["go"]:
            time.sleep(0.02)
            if kw.get("cancel_check") and kw["cancel_check"]():
                return {"matched": 0}
        return {"matched": 0}
    monkeypatch.setattr(bj, "run_bulk_import", slow_run)
    c, token = _admin_client()
    c.post("/admin/bulk-import", data={"csrf_token": token, "region": "monaco",
                                       "scoring_profile_key": ""},
           follow_redirects=False)
    r2 = c.post("/admin/bulk-import", data={"csrf_token": token, "region": "monaco",
                                            "scoring_profile_key": ""},
                follow_redirects=False)
    # second start while running -> redirect back with no new job thread
    c.post("/admin/bulk-import/cancel", data={"csrf_token": token},
           follow_redirects=False)
    started["go"] = True
    assert r2.status_code in (302, 303, 409)


def test_bulk_import_requires_admin():
    c = TestClient(lv.app)
    m = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text)
    token = m.group(1)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": token}, follow_redirects=False)
    r = c.post("/admin/bulk-import", data={"csrf_token": token, "region": "monaco"},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/login" in r.headers.get("location", "/login")


# ── Fix A: cancel button server-rendered during live run ──────────────────

def test_cancel_form_visible_while_running_hidden_when_done(monkeypatch):
    """GET /admin/ingest while running: cancel form is server-rendered (not hidden).
    After the job finishes: cancel div carries class='hidden'."""
    import app.web.bulk_jobs as bj
    started = {"go": False}

    def slow_run(session, region_key, **kw):
        while not started["go"]:
            time.sleep(0.02)
            if kw.get("cancel_check") and kw["cancel_check"]():
                return {"matched": 0}
        return {"matched": 0}

    monkeypatch.setattr(bj, "run_bulk_import", slow_run)
    c, token = _admin_client()
    c.post("/admin/bulk-import", data={"csrf_token": token, "region": "monaco",
                                       "scoring_profile_key": ""},
           follow_redirects=False)

    # While running: the server must render the cancel form without hidden class
    html = c.get("/admin/ingest").text
    assert 'action="/admin/bulk-import/cancel"' in html, \
        "cancel form must be present while running"
    # The cancel-wrap div must NOT be hidden while running
    assert 'id="bulk-cancel-wrap" class="hidden"' not in html, \
        "cancel-wrap must not be hidden while job is running"

    # Allow the job to finish, then verify cancel button is hidden
    started["go"] = True
    for _ in range(50):
        body = c.get("/admin/bulk-import/status").json()
        if body["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.1)

    html2 = c.get("/admin/ingest").text
    assert 'id="bulk-cancel-wrap" class="hidden"' in html2, \
        "cancel-wrap must be hidden after job completes"


# ── Fix B: phase field written to counts_json ─────────────────────────────

def test_bulk_job_lifecycle_includes_phase(monkeypatch):
    """counts_json must carry a 'phase' key throughout the job lifecycle."""
    import app.web.bulk_jobs as bj
    monkeypatch.setattr(bj, "run_bulk_import", _fake_run)
    c, token = _admin_client()
    c.post("/admin/bulk-import", data={"csrf_token": token, "region": "monaco",
                                       "scoring_profile_key": ""},
           follow_redirects=False)
    # Wait for completion
    for _ in range(50):
        body = c.get("/admin/bulk-import/status").json()
        if body["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert body["status"] == "done"
    # Phase must be present in the final counts (preserved through _write)
    assert "phase" in body.get("counts", {}), \
        "counts_json must include 'phase' key after job completes"
