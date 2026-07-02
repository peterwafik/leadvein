"""Generic channel profiles + honest intersection with campaign profiles.

User requirement: if a campaign requires validated phone AND the buyer picks
"reach by email", the result requires BOTH (fewer leads) — never a silent override.
"""
from __future__ import annotations

import json
import pytest

from app.core.db import Lead
from app.core.targeting.view import lead_view
from app.quality.gate import clears_gate
from app.quality.profiles.combine import combine_profiles
from app.quality.profiles.registry import get as get_profile
from app.quality.profiles.utilities import UTILITIES


def _view(**val):
    return lead_view(Lead(business_name="X", validation_json=json.dumps(val)))


def test_three_generic_profiles_registered():
    import app.quality.runtime as qr
    qr.register_quality_runtime()
    for key in ("phone_validated", "email_validated", "contact_validated"):
        assert get_profile(key).required


def test_combine_takes_max_tier_per_field_and_unions_fields():
    import app.quality.runtime as qr
    qr.register_quality_runtime()
    combined = combine_profiles([UTILITIES, get_profile("email_validated")])
    assert combined.required["phone"] == "validated"     # from campaign
    assert combined.required["email"] == "validated"     # from channel choice
    assert combined.required["profile"] == "present"


def test_intersection_holds_back_partial_leads():
    """Campaign wants validated phone; buyer picks email channel → need BOTH."""
    import app.quality.runtime as qr
    qr.register_quality_runtime()
    combined = combine_profiles([UTILITIES, get_profile("email_validated")])
    only_email = _view(profile={"tier": "validated"},
                       email={"tier": "validated"}, phone={"tier": "present"})
    only_phone = _view(profile={"tier": "validated"},
                       phone={"tier": "validated"}, email={"tier": "present"})
    both = _view(profile={"tier": "validated"},
                 phone={"tier": "validated"}, email={"tier": "validated"})
    assert clears_gate(only_email, combined) is False
    assert clears_gate(only_phone, combined) is False
    assert clears_gate(both, combined) is True


def test_combine_never_lowers_a_tier():
    import app.quality.runtime as qr
    qr.register_quality_runtime()
    a = get_profile("phone_validated")
    from app.quality.profiles.base import QualityProfile
    weaker = QualityProfile(key="w", label="w", required={"phone": "present"})
    combined = combine_profiles([a, weaker])
    assert combined.required["phone"] == "validated"


def test_combine_empty_raises():
    with pytest.raises(ValueError):
        combine_profiles([])
    with pytest.raises(ValueError):
        combine_profiles([None])
