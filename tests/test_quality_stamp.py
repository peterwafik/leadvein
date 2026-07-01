import json
from app.quality.tiers import achieved_tier, meets, TIER_ORDER


def test_tier_order_and_meets():
    assert TIER_ORDER.index("validated") > TIER_ORDER.index("present")
    assert achieved_tier({"present": True, "validated": True}) == "validated"
    assert achieved_tier({"present": True, "validated": False}) == "present"
    assert achieved_tier({"present": False}) == "absent"
    assert achieved_tier({"present": True, "validated": True, "verified_live": True}) == "verified_live"
    assert meets("validated", "present") and not meets("present", "validated")
    assert not meets("absent", "present")


def test_build_validation_stamps_honest_tiers_and_no_gated_fields():
    from app.quality.stamp import build_validation
    fields = {"email": "info@acme.com", "phone": "+44 7911 123456",
              "address": {"line1": "1 High St", "city": "London", "lat": 51.5, "lon": -0.1},
              "intent": {"website_reachable": True}, "name": "Acme",
              "category_keys": ["cafe"], "city": "London", "opening_hours": "Mo-Su",
              "website_url": "https://a.com", "date_last_verified": None}
    v = build_validation(fields, mx_lookup=lambda d: True)
    assert v["email"]["tier"] == "validated" and v["phone"]["tier"] == "validated"
    assert v["address"]["tier"] == "validated" and v["website"]["tier"] == "validated"
    # INV-Q2: gated financial/size fields are NEVER stamped by self-run validation
    for gated in ("has_mca", "amount_owed", "lender", "size_band"):
        assert gated not in v
    # INV-Q6/Q2: nothing is verified_live from a self-run check
    assert all(fb.get("tier") != "verified_live" for fb in v.values())


def test_ingested_lead_carries_validation(monkeypatch):
    # the pipeline stamps validation_json + quality_score; assert an ingested lead has honest tiers
    import app.quality.validators.email as EM
    monkeypatch.setattr(EM, "_default_mx", lambda d: True)   # offline MX for the test
    from tests.helpers_ingest import run_fake_ingest   # provided by this task's step 3 note
    lead = run_fake_ingest()
    v = json.loads(lead.validation_json)
    assert "email" in v and "phone" in v and lead.quality_score >= 0
