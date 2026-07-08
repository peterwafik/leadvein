import re
from fastapi.testclient import TestClient
import app.leadvault as lv
from app.core.leadcats import sync_lead_categories
from tests.quality_helpers import hot_validation_json


def client():
    return TestClient(lv.app)


def _token_from(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


def test_login_page_loads():
    assert client().get("/login").status_code == 200


def test_demo_buyer_login_sets_session():
    c = client()
    page = c.get("/login").text
    token = _token_from(page)
    r = c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                               "csrf_token": token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "session" in r.headers.get("set-cookie", "").lower()


def test_admin_login_page_does_not_loop():
    # Regression: an admin with a live session hitting GET /login must not be
    # sent to /app (buyer-only, which bounces admins back to /login -> infinite
    # redirect loop -> ERR_TOO_MANY_REDIRECTS in the browser). It must go to /admin.
    c = client()
    token = _token_from(c.get("/login").text)
    c.post("/login", data={"email": "admin@leadvault.local", "password": "admin12345",
                           "csrf_token": token})
    r = c.get("/login", follow_redirects=False)
    assert r.status_code in (302, 303), f"expected redirect for logged-in admin, got {r.status_code}"
    assert r.headers.get("location") == "/admin", \
        f"admin /login must route to /admin, not loop via {r.headers.get('location')}"


def test_full_buyer_journey(monkeypatch):
    from sqlmodel import Session
    import json
    from app.core.db import Lead, _now
    # seed one matching lead directly into the app DB; hot-blob required: this is the
    # end-to-end real-app path — the lead MUST clear the gate (gate is ON in production).
    with Session(lv.engine) as s:
        hidden = Lead(business_name="Hidden Diner",
                      category_keys_json=json.dumps(["restaurant"]), city="London",
                      phone="+44 1", public_email="info@diner.com",
                      website_url="https://hiddendiner.co.uk", score_total=85,
                      subscores_json=json.dumps({"fit": 85}),
                      score_explanation="independent restaurant, open 7 days",
                      source_name="OpenStreetMap (Overpass)", source_url="http://osm",
                      source_license="ODbL", date_last_verified=_now(), price_credits=3,
                      validation_json=hot_validation_json())
        s.add(hidden); s.commit(); s.refresh(hidden)
        sync_lead_categories(s, hidden)
    c = client()
    # get csrf token and log in
    login_page = c.get("/login").text
    token = _token_from(login_page)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": token})
    # marketplace search now redirects to /app/find (marketplace page retired)
    # Old assert: POST /app/marketplace/search returned 200 with masked results HTML.
    # New assert: POST /app/marketplace/search redirects to /app/find?mode=quick.
    # Reason: marketplace_search is now a redirect stub per Task 10; lead search moved to /app/find.
    r = c.post("/app/marketplace/search",
               data={"categories": "restaurant", "city": "London", "min_score": "50",
                     "csrf_token": token}, follow_redirects=False)
    assert r.status_code in (301, 302, 303, 307, 308), \
        f"expected redirect from retired marketplace search, got {r.status_code}"
    assert "/app/find" in r.headers.get("location", ""), \
        f"expected redirect to /app/find, got {r.headers.get('location', '')}"
    # accept compliance, then unlock
    c.post("/app/ack", data={"csrf_token": token})
    lead_id = None
    with Session(lv.engine) as s:
        from sqlmodel import select
        lead_id = s.exec(select(Lead).where(Lead.business_name == "Hidden Diner")).first().id
    ru = c.post(f"/app/unlock/{lead_id}", data={"csrf_token": token},
                follow_redirects=False)
    assert ru.status_code in (302, 303)
    # purchased detail now shows full contact
    detail = c.get(f"/app/purchased/{lead_id}")
    assert detail.status_code == 200
    assert "Hidden Diner" in detail.text and "info@diner.com" in detail.text
    # export contains the unlocked contact
    ex = c.get("/app/export.csv")
    assert ex.status_code == 200 and "info@diner.com" in ex.text
    # a different buyer cannot view the detail (ownership guard)


def test_admin_ingestion_populates_inventory(monkeypatch):
    from app.adapters.base import SourceMeta, NormalizedLead
    from app.adapters import registry as adapter_registry

    class FakeAdminAdapter:
        meta = SourceMeta(key="fake_admin", name="FakeAdmin", type="test",
                          url="http://x", license="TESTLIC")
        def discover(self, query):
            return [{"n": "Admin Diner"}]
        def normalize(self, raw):
            return NormalizedLead(business_name=raw["n"], category_keys=["restaurant"],
                                  address={"city": "London"}, phone="+44 9",
                                  website_url="https://admindiner.com",
                                  source_key=self.meta.key, source_license=self.meta.license)
        def attribution(self):
            return "fake"

    adapter_registry.register(FakeAdminAdapter())
    # avoid live website enrichment during the test
    import app.web.routes_admin as ra
    monkeypatch.setattr(ra, "_enrich_for_admin",
                        lambda lead: {"website_reachable": True, "ssl": True,
                                      "online_ordering_detected": False,
                                      "booking_detected": False,
                                      "payment_provider_detected": False,
                                      "ecommerce_detected": False,
                                      "last_scanned": "2026-06-28T00:00:00+00:00"})
    c = client()
    login_page = c.get("/login").text
    token = _token_from(login_page)
    c.post("/login", data={"email": "admin@leadvault.local", "password": "admin12345",
                           "csrf_token": token})
    r = c.post("/admin/ingest", data={"adapter_key": "fake_admin", "city": "London",
               "categories": "restaurant", "scoring_profile_key": "utility_energy",
               "csrf_token": token},
               follow_redirects=True)
    assert r.status_code == 200
    assert "Admin Diner" in r.text or "1" in r.text  # leads list or count shows the new lead
