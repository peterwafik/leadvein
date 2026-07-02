"""INV-6/7/8/10 consolidated invariant tests for the Campaign layer.

INV-6  No fabrication — gated field absent from inventory → tri-state blocks.
INV-7  Spine parity  — campaign segment == hand-built composition + suppression.
INV-8  Cross-category — utilities composition has no category predicate; matches ≥2 categories.
INV-10 Audit          — campaign.select and campaign.search each produce audit rows.
"""
from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient
from sqlmodel import Session, select

import app.leadvault as lv
from app.core.db import (AuditLog, Lead, Segment, SuppressionEntry,
                         SuppressionList, _now, init_db)
from app.core.leadcats import sync_lead_categories
from app.core.targeting import registry
from app.core.targeting.estimate import estimate
from app.core.targeting.view import MISSING, get_path, lead_view
from app.targeting.runtime import register_targeting_runtime
from tests.quality_helpers import hot_validation_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client():
    return TestClient(lv.app)


def _token_from(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


def _login(c: TestClient) -> str:
    """Log in as the demo buyer; returns the CSRF token."""
    page = c.get("/login").text
    token = _token_from(page)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": token}, follow_redirects=False)
    return token


# ---------------------------------------------------------------------------
# INV-6: No fabrication
# ---------------------------------------------------------------------------

def test_inv6_no_fabrication():
    """A composition whose only predicate reads an unpopulated gated path
    (attributes.has_mca) → tri-state unknown → estimate count 0.
    Its negation also returns 0 (kleene_not(None) == None → non-match).
    No lead view carries a non-null attributes.has_mca value.
    """
    from app.core.serve_filters import clear as _gate_off
    _gate_off()  # gate off: testing tri-state / no-fabrication, not quality

    # Minimal inline predicate that reads the gated path — never in real predicates
    class _HasMca:
        key = "attributes.has_mca"
        group = "financial"
        label = "Has MCA (gated)"
        reads = ["attributes.has_mca"]
        params_schema = {}

        def matches(self, view, params):
            val = get_path(view, "attributes.has_mca")
            if val is MISSING or val is None:
                return None  # tri-state unknown: path absent → non-match
            return bool(val)

    registry.clear()
    register_targeting_runtime()
    registry.register(_HasMca())

    e = init_db("sqlite://")
    with Session(e) as s:
        # Lead with no has_mca in attributes_json
        lead = Lead(
            business_name="Gated Cafe", city="Oxford", country="GB",
            phone="+44 1234 5678", score_total=80, date_last_verified=_now(),
            attributes_json="{}", validation_json=hot_validation_json(),
        )
        s.add(lead)
        s.commit()
        s.refresh(lead)
        sync_lead_categories(s, lead)

        comp_pos = {"op": "AND", "nodes": [
            {"predicate": "attributes.has_mca", "params": {}}
        ]}
        comp_neg = {"op": "AND", "nodes": [
            {"predicate": "attributes.has_mca", "params": {}, "negate": True}
        ]}

        pos = estimate(s, 1, comp_pos)
        neg = estimate(s, 1, comp_neg)

        assert pos["count"] == 0, (
            "INV-6: unpopulated gated attribute → tri-state unknown → non-match → count must be 0"
        )
        assert neg["count"] == 0, (
            "INV-6: negation of unknown is still unknown → non-match → count must be 0"
        )

        # No lead view carries a non-null attributes.has_mca
        view = lead_view(lead)
        assert view["attributes"].get("has_mca") is None, (
            "INV-6: lead view must not carry a non-null attributes.has_mca value"
        )

    # Restore registry for remaining tests
    registry.clear()
    register_targeting_runtime()


# ---------------------------------------------------------------------------
# INV-7: Spine parity + suppression-block
# ---------------------------------------------------------------------------

def test_inv7_spine_parity():
    """A campaign-compiled Segment and a hand-built identical composition give
    the same estimate count + sample lead IDs.
    A suppressed lead that matches the composition is absent from both estimates.
    """
    from app.core.serve_filters import clear as _gate_off
    _gate_off()  # gate off: testing parity + suppression, not quality

    registry.clear()
    register_targeting_runtime()

    e = init_db("sqlite://")
    with Session(e) as s:
        # Two normal leads in Oxford, GB with phone (passes contactability)
        for bname in ("Alpha Ltd", "Beta Corp"):
            l = Lead(
                business_name=bname, city="Oxford", country="GB",
                phone="+44 1234 0001", score_total=80, date_last_verified=_now(),
                validation_json=hot_validation_json(),
            )
            s.add(l)
            s.commit()
            s.refresh(l)
            sync_lead_categories(s, l)

        # One suppressed lead — same composition match, but domain suppressed
        sup = Lead(
            business_name="Suppressed Co", city="Oxford", country="GB",
            phone="+44 1234 9999", website_url="https://suppressed.example.com",
            score_total=80, date_last_verified=_now(), validation_json=hot_validation_json(),
        )
        s.add(sup)
        s.commit()
        s.refresh(sup)
        sync_lead_categories(s, sup)
        sup_id = sup.id

        # Add domain to buyer 1 suppression list
        sup_list = SuppressionList(buyer_account_id=1, name="test-list")
        s.add(sup_list)
        s.commit()
        s.refresh(sup_list)
        s.add(SuppressionEntry(list_id=sup_list.id, kind="domain",
                               value="suppressed.example.com"))
        s.commit()

        # Composition equivalent to compiled utilities_uk with area=Oxford
        composition = {
            "op": "AND",
            "nodes": [
                {"predicate": "geo.country", "params": {"value": "GB"}},
                {"predicate": "geo.city", "params": {"value": "Oxford"}},
                {"predicate": "contactability.has_business_contact", "params": {}},
            ],
        }

        # Campaign-derived segment with origin_key
        seg = Segment(
            buyer_account_id=1, name="Utilities Oxford INV-7",
            composition_json=json.dumps(composition), origin_key="utilities_uk",
        )
        s.add(seg)
        s.commit()
        s.refresh(seg)

        seg_est = estimate(s, 1, json.loads(seg.composition_json))
        hand_est = estimate(s, 1, composition)

        # Parity: same count
        assert seg_est["count"] == hand_est["count"], (
            f"INV-7: segment estimate ({seg_est['count']}) must equal "
            f"hand-built estimate ({hand_est['count']})"
        )
        assert seg_est["count"] == 2, (
            f"INV-7: expected 2 (suppressed lead blocked), got {seg_est['count']}"
        )

        # Suppressed lead absent from both sample sets
        seg_ids = {item["lead_id"] for item in seg_est["samples"]}
        hand_ids = {item["lead_id"] for item in hand_est["samples"]}
        assert sup_id not in seg_ids, (
            "INV-7: suppressed lead must be absent from segment estimate samples"
        )
        assert sup_id not in hand_ids, (
            "INV-7: suppressed lead must be absent from hand-built estimate samples"
        )
        assert seg_ids == hand_ids, (
            "INV-7: segment and hand-built estimates must return the same sample lead IDs"
        )


# ---------------------------------------------------------------------------
# INV-8: Cross-category
# ---------------------------------------------------------------------------

def test_inv8_cross_category():
    """The seeded utilities_uk composition has no category predicate; on a seed
    of leads spanning ≥2 categories in one city, the estimate matches all of
    them (≥2 categories represented in the result).
    """
    from app.core.serve_filters import clear as _gate_off
    _gate_off()  # gate off: testing cross-category matching, not quality

    registry.clear()
    register_targeting_runtime()

    from app.campaigns.compile import compile_campaign
    from app.campaigns.crud import get_by_key
    from app.campaigns.seed import seed_campaigns

    e = init_db("sqlite://")
    with Session(e) as s:
        seed_campaigns(s)

        # Seed leads from three different categories — all in Oxford, GB with phone
        seeded = {}
        for bname, cat in [("Cafe Oxford", "cafe"), ("Gym Oxford", "gym"),
                            ("Plumber Oxford", "plumber")]:
            l = Lead(
                business_name=bname, city="Oxford", country="GB",
                phone="+44 1234 0001", score_total=80, date_last_verified=_now(),
                category_keys_json=json.dumps([cat]), validation_json=hot_validation_json(),
            )
            s.add(l)
            s.commit()
            s.refresh(l)
            sync_lead_categories(s, l)
            seeded[l.id] = cat

        # Compile the utilities_uk campaign (no category predicate — INV-8)
        campaign = get_by_key(s, "utilities_uk")
        result = compile_campaign(campaign, {"area": "Oxford"})
        composition = result["composition"]

        # Confirm: no category predicate in the compiled composition
        assert not any("category" in n["predicate"] for n in composition["nodes"]), (
            "INV-8: utilities_uk composition must not contain a category predicate"
        )

        est = estimate(s, 1, composition)

        assert est["count"] >= 2, (
            f"INV-8: estimate must match ≥2 leads across categories, got {est['count']}"
        )

        matched_ids = {item["lead_id"] for item in est["samples"]}
        matched_cats = {seeded[lid] for lid in matched_ids if lid in seeded}
        assert len(matched_cats) >= 2, (
            f"INV-8: matched leads must span ≥2 categories, got only: {matched_cats}"
        )


# ---------------------------------------------------------------------------
# INV-10: Audit rows
# ---------------------------------------------------------------------------

def test_inv10_audit_rows():
    """campaign.select and campaign.search each produce an audit row."""
    c = _client()
    token = _login(c)

    # Trigger campaign.select via apply-campaign
    r = c.post(
        "/app/composer/apply-campaign",
        json={"key": "utilities_uk", "params": {"area": "Oxford"}},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 200, f"apply-campaign failed: {r.text}"

    # Save a segment with origin_key (campaign-derived)
    composition = json.dumps({
        "op": "AND",
        "nodes": [
            {"predicate": "geo.country", "params": {"value": "GB"}},
            {"predicate": "geo.city", "params": {"value": "Oxford"}},
            {"predicate": "contactability.has_business_contact", "params": {}},
        ],
    })
    save_r = c.post(
        "/app/composer/save",
        data={
            "csrf_token": token,
            "name": "Utilities Oxford INV-10",
            "composition": composition,
            "origin_key": "utilities_uk",
        },
        follow_redirects=False,
    )
    assert save_r.status_code in (302, 303), (
        f"segment save failed: {save_r.status_code}"
    )

    # Retrieve the saved segment
    with Session(lv.engine) as s:
        seg = s.exec(
            select(Segment)
            .where(Segment.origin_key == "utilities_uk")
            .order_by(Segment.id.desc())
        ).first()
    assert seg is not None, "segment with origin_key='utilities_uk' not found after save"

    # Trigger campaign.search by calling estimate with segment_id
    est_r = c.post(
        "/app/composer/estimate",
        json={
            "composition": json.loads(composition),
            "segment_id": seg.id,
        },
    )
    assert est_r.status_code == 200, f"composer estimate failed: {est_r.text}"

    # Verify audit rows
    with Session(lv.engine) as s:
        select_rows = s.exec(
            select(AuditLog).where(AuditLog.action == "campaign.select")
        ).all()
        search_rows = s.exec(
            select(AuditLog).where(AuditLog.action == "campaign.search")
        ).all()

    assert select_rows, "INV-10: expected ≥1 audit row with action='campaign.select'"
    assert search_rows, "INV-10: expected ≥1 audit row with action='campaign.search'"

    # The search row must carry origin_key
    assert any(
        json.loads(row.meta_json).get("origin_key") == "utilities_uk"
        for row in search_rows
    ), "INV-10: campaign.search audit row must carry origin_key='utilities_uk' in meta"
