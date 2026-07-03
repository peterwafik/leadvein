from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient
from sqlmodel import Session

import app.leadvault as lv
from app.core.db import Lead
from app.core.masking import mask_preview


def _lead(**kw):
    v = {"profile": {"tier": "validated"},
         "phone": {"tier": "validated", "line_type": "fixed_line"},
         "email": {"tier": "present"},
         "address": {"tier": "present"},
         "website": {"tier": "validated"}}
    defaults = dict(business_name="Vis Bakery", city="Cambridge", country="GB",
                    phone="+441223000000", public_email="hello@visbakery.example",
                    category_keys_json='["bakery"]',
                    validation_json=json.dumps(v),
                    attributes_json=json.dumps({"recipe_key": "gloriafood",
                                                "match_strength": 3}))
    defaults.update(kw)
    return Lead(**defaults)


def test_mask_preview_exposes_tiers_never_values():
    p = mask_preview(_lead())
    assert p["quality"]["phone"]["tier"] == "validated"
    assert p["quality"]["phone"]["line_type"] == "fixed_line"
    assert p["quality"]["email"]["tier"] == "present"
    assert p["tech_match"] == {"recipe_key": "gloriafood", "strength": 3}
    blob = json.dumps(p)
    assert "+441223000000" not in blob          # masking holds
    assert "visbakery.example" not in blob


def test_mask_preview_never_shows_verified_live_from_self_run():   # INV-Q2
    lead = _lead()
    p = mask_preview(lead)
    assert all(f.get("tier") != "verified_live" for f in p["quality"].values())


def test_lead_detail_renders_tiers_and_locked_verified():
    with Session(lv.engine) as s:
        lead = _lead()
        s.add(lead); s.commit(); s.refresh(lead)
        lead_id = lead.id
    c = TestClient(lv.app)
    m = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text)
    c.post("/login", data={"email": "buyer@demo.local", "password": "buyer12345",
                           "csrf_token": m.group(1)}, follow_redirects=False)
    # own the lead so detail renders (insert PurchasedLead directly)
    from app.core.db import PurchasedLead, User
    from sqlmodel import select
    with Session(lv.engine) as s:
        u = s.exec(select(User).where(User.email == "buyer@demo.local")).first()
        s.add(PurchasedLead(buyer_account_id=u.buyer_account_id, lead_id=lead_id,
                            price_paid_credits=1))
        s.commit()
    html = c.get(f"/app/purchased/{lead_id}").text
    assert "Validated" in html
    assert "format + line type" in html
    assert "Verified-live" in html and "requires licensed provider" in html
    assert "data-tier-locked" in html
