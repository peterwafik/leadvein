import json
import re
from sqlmodel import Session
from app.core.db import init_db, Lead, _now
from app.core.leadcats import sync_lead_categories
from app.core.targeting import registry
from app.targeting.runtime import register_targeting_runtime
from app.core.targeting.coverage import recompute_coverage
from app.core.targeting.composer import predicate_options


def test_options_are_data_driven():
    registry.clear(); register_targeting_runtime()
    e = init_db("sqlite://")
    with Session(e) as s:
        lead = Lead(business_name="A", country="GB", city="Oxford", phone="1", score_total=80,
                    category_keys_json=json.dumps(["cafe"]), date_last_verified=_now(),
                    intent_json="{}")   # NOTE: no intent signals populated
        s.add(lead); s.commit(); s.refresh(lead); sync_lead_categories(s, lead)
        recompute_coverage(s)
        opt = predicate_options(s)
        avail = {d["key"] for d in opt["available"]}
        unavail = {d["key"] for d in opt["unavailable"]}
        assert "geo.country" in avail and "geo.city" in avail and "quality.min_score" in avail
        # web.has_signal reads "intent" which is NOT populated -> unavailable (greyed), not faked
        assert "web.has_signal" in unavail
        assert avail.isdisjoint(unavail)


# ── Web route tests: save / list / load / delete Segments ─────────────────


def _client():
    import app.leadvault as lv
    from fastapi.testclient import TestClient
    return TestClient(lv.app)


def _token_from(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


def _login_buyer(c):
    """Log in as demo buyer; return (client, csrf_token)."""
    login_page = c.get("/login").text
    token = _token_from(login_page)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": token})
    return token


def test_save_segment_creates_and_lists():
    """POST /app/composer/save stores a Segment; GET /app/audiences lists it."""
    # Old assert: redirect to /app/segments, then GET /app/segments renders 200 with name.
    # New assert: redirect to /app/audiences (segments retired); /app/audiences renders name.
    # Reason: composer_save and segments_page both redirect to /app/audiences per Task 10.
    import app.leadvault as lv
    from sqlmodel import select
    from app.core.db import User
    from app.core.targeting.segments import list_segments

    c = _client()
    token = _login_buyer(c)

    composition = {"op": "AND", "nodes": [
        {"predicate": "geo.country", "params": {"value": "GB"}, "negate": False}
    ]}

    # POST save — now redirects to /app/audiences (not /app/segments)
    r = c.post("/app/composer/save", data={
        "csrf_token": token,
        "name": "UK Leads",
        "composition": json.dumps(composition),
    }, follow_redirects=False)
    assert r.status_code in (302, 303), f"expected redirect, got {r.status_code}"
    assert "/app/audiences" in r.headers.get("location", "")

    # Verify it exists in the DB under the demo buyer account
    with Session(lv.engine) as s:
        buyer = s.exec(select(User).where(User.email == "buyer@demo.local")).first()
        ba_id = buyer.buyer_account_id
        segs = list_segments(s, ba_id)
        names = [seg.name for seg in segs]
        assert "UK Leads" in names, f"expected 'UK Leads' in {names}"
        seg = next(seg for seg in segs if seg.name == "UK Leads")
        assert json.loads(seg.composition_json) == composition

    # GET /app/audiences renders the segment name (new unified page)
    page = c.get("/app/audiences")
    assert page.status_code == 200
    assert "UK Leads" in page.text


def test_segment_ownership_and_delete_isolation():
    """A second buyer cannot see or delete another buyer's segment."""
    import app.leadvault as lv
    from sqlmodel import select
    from app.core.db import User, BuyerAccount
    from app.core.targeting.segments import list_segments, get_owned, create_segment, delete_segment

    # Create segment directly for buyer account 999 (non-existent BA id)
    with Session(lv.engine) as s:
        # Create a throwaway buyer account
        ba2 = BuyerAccount(company_name="Isolated Buyer", credits=0)
        s.add(ba2); s.commit(); s.refresh(ba2)
        ba2_id = ba2.id

        comp = {"op": "AND", "nodes": [
            {"predicate": "geo.country", "params": {"value": "DE"}, "negate": False}
        ]}
        # Create segment for demo buyer (ba_id 1 if seeded first — but use the real id)
        buyer_user = s.exec(select(User).where(User.email == "buyer@demo.local")).first()
        ba_owner_id = buyer_user.buyer_account_id

        seg = create_segment(s, ba_owner_id, "DE Leads Isolation Test", comp)

        # Second buyer (ba2) cannot see owner's segments
        assert list_segments(s, ba2_id) == []

        # Non-owner delete is a no-op: get_owned returns None for ba2
        assert get_owned(s, seg.id, ba2_id) is None
        result = delete_segment(s, seg.id, ba2_id)
        assert result is False

        # Segment still exists for the owner
        assert get_owned(s, seg.id, ba_owner_id) is not None


def test_delete_segment_via_http():
    """POST /app/segments/{id}/delete removes the segment and redirects to /app/audiences."""
    # Old assert: redirect location contains /app/segments.
    # New assert: redirect location contains /app/audiences (segment listing moved there).
    # Reason: segment_delete final redirect updated to /app/audiences per Task 10.
    import app.leadvault as lv
    from sqlmodel import select
    from app.core.db import User
    from app.core.targeting.segments import create_segment, get_owned, list_segments

    c = _client()
    token = _login_buyer(c)

    # Create segment directly
    with Session(lv.engine) as s:
        buyer_user = s.exec(select(User).where(User.email == "buyer@demo.local")).first()
        ba_id = buyer_user.buyer_account_id
        comp = {"op": "AND", "nodes": []}
        seg = create_segment(s, ba_id, "To Be Deleted", comp)
        seg_id = seg.id

    # Delete via HTTP — now redirects to /app/audiences (not /app/segments)
    r = c.post(f"/app/segments/{seg_id}/delete", data={"csrf_token": token},
               follow_redirects=False)
    assert r.status_code in (302, 303), f"expected redirect, got {r.status_code}"
    assert "/app/audiences" in r.headers.get("location", "")

    # Verify it is gone
    with Session(lv.engine) as s:
        buyer_user = s.exec(select(User).where(User.email == "buyer@demo.local")).first()
        ba_id = buyer_user.buyer_account_id
        assert get_owned(s, seg_id, ba_id) is None


def test_composer_get_with_segment_preset():
    """GET /app/composer?segment=<id> redirects to /app/find?audience=<id>."""
    # Old assert: GET /app/composer?segment=N returned 200 with window._segmentPreset in HTML.
    # New assert: GET /app/composer?segment=N redirects to /app/find?audience=N (composer retired).
    # Reason: /app/composer is now a redirect stub; segment preset loading moved to /app/find.
    import app.leadvault as lv
    from sqlmodel import select
    from app.core.db import User
    from app.core.targeting.segments import create_segment

    c = _client()
    token = _login_buyer(c)

    with Session(lv.engine) as s:
        buyer_user = s.exec(select(User).where(User.email == "buyer@demo.local")).first()
        ba_id = buyer_user.buyer_account_id
        comp = {"op": "AND", "nodes": [
            {"predicate": "geo.city", "params": {"value": "London"}, "negate": False}
        ]}
        seg = create_segment(s, ba_id, "London Test Segment", comp)
        seg_id = seg.id

    # GET composer with segment param — must now redirect carrying audience=<id>
    r = c.get(f"/app/composer?segment={seg_id}", follow_redirects=False)
    assert r.status_code in (301, 302, 303, 307, 308), \
        f"expected redirect from retired /app/composer, got {r.status_code}"
    location = r.headers.get("location", "")
    assert location.startswith("/app/find"), f"expected redirect to /app/find, got {location}"
    assert f"audience={seg_id}" in location, \
        f"expected audience={seg_id} in redirect location, got {location}"


def test_composer_estimate_bad_predicate_returns_400():
    """Unknown predicate → 400 not 500; valid empty composition → 200."""
    c = _client()
    _login_buyer(c)

    # Unknown predicate: must return 400 (not 500 / KeyError)
    bad = {"composition": {"op": "AND", "nodes": [
        {"predicate": "does.not.exist", "params": {}}
    ]}}
    r = c.post("/app/composer/estimate", json=bad)
    assert r.status_code == 400, f"expected 400 for unknown predicate, got {r.status_code}"

    # Valid (empty) composition: must return 200
    good = {"composition": {"op": "AND", "nodes": []}}
    r2 = c.post("/app/composer/estimate", json=good)
    assert r2.status_code == 200, f"expected 200 for valid composition, got {r2.status_code}"
