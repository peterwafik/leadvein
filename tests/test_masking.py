import json
from sqlmodel import Session
from app.core.db import init_db, Lead, PurchasedLead
from app.core.masking import mask_preview, unlock_view, is_owned, assert_owned
import pytest


def test_preview_never_leaks_contact():
    lead = Lead(business_name="Secret Diner", category_keys_json=json.dumps(["restaurant"]),
                city="London", phone="+44 1", public_email="x@y.com",
                website_url="https://secret.com", score_total=80,
                subscores_json=json.dumps({"fit": 80}), score_explanation="because",
                source_name="OpenStreetMap (Overpass)", price_credits=3)
    p = mask_preview(lead)
    blob = json.dumps(p).lower()
    assert "secret diner" not in blob
    assert "secret.com" not in blob and "x@y.com" not in blob and "+44 1" not in blob
    assert p["has_phone"] is True and p["has_email"] is True and p["has_website"] is True
    assert p["score_total"] == 80 and p["reason"] == "because"
    assert p["city"] == "London" and p["price_credits"] == 3


def test_unlock_view_has_contact():
    lead = Lead(business_name="D", phone="+44 1", public_email="x@y.com",
                website_url="https://s.com", source_url="http://src", source_license="ODbL")
    u = unlock_view(lead)
    assert u["business_name"] == "D" and u["phone"] == "+44 1"
    assert u["source_license"] == "ODbL"


def test_ownership_guard():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        s.add(PurchasedLead(buyer_account_id=1, lead_id=5))
        s.commit()
        assert is_owned(s, 1, 5) is True
        assert is_owned(s, 2, 5) is False
        assert_owned(s, 1, 5)  # no raise
        with pytest.raises(PermissionError):
            assert_owned(s, 2, 5)
