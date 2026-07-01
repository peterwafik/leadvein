from app.core.db import Lead
from app.core.targeting.view import lead_view
from app.quality.gate import clears_gate
from app.quality.profiles.baseline import BASELINE
from app.quality.profiles.base import QualityProfile
import json


def _view(**val):
    return lead_view(Lead(business_name="X", validation_json=json.dumps(val)))


def test_clears_baseline_when_profile_and_contact_validated():
    v = _view(profile={"tier": "validated"}, email={"tier": "validated"},
              phone={"tier": "present"})
    assert clears_gate(v, BASELINE) is True


def test_held_back_when_required_field_below_tier_or_absent():   # INV-Q4
    # contact only "present" (not validated) -> held back
    v1 = _view(profile={"tier": "validated"}, email={"tier": "present"}, phone={"tier": "present"})
    assert clears_gate(v1, BASELINE) is False
    # profile absent entirely -> unknown -> held back
    v2 = _view(email={"tier": "validated"})
    assert clears_gate(v2, BASELINE) is False


def test_verified_live_requirement_never_met_without_provider():   # INV-Q2
    strict = QualityProfile(key="strict", label="Strict",
                            required={"email": "verified_live"}, weights={"email": 100})
    # best a self-run check can do is "validated" -> never meets verified_live -> held back
    v = _view(email={"tier": "validated"})
    assert clears_gate(v, strict) is False
