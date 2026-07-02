"""Shared test helpers for the lead quality gate.

`HOT_VALIDATION` is an honest validation blob that clears the BASELINE quality profile
(profile present + a validated business contact). Use it to seed test leads that are
MEANT to represent real, surfaced hot leads when the gate is ON — this is the
"seed an honest validation blob" option for root-causing gate-on breakage, as opposed
to the "explicit reasoned gate-off" option (calling app.core.serve_filters.clear() with
a comment) for tests where lead quality is orthogonal to what they exercise.
"""
import json

HOT_VALIDATION = {
    "profile": {"present": True, "validated": True, "tier": "validated"},
    "email": {"present": True, "validated": True, "tier": "validated"},
    "phone": {"present": True, "validated": True, "tier": "validated"},
    "address": {"present": True, "validated": True, "tier": "validated"},
    "website": {"present": True, "validated": True, "tier": "validated"},
    "freshness": {"present": True, "validated": True, "tier": "validated"},
}


def hot_validation_json() -> str:
    return json.dumps(HOT_VALIDATION)


PHONE_VALIDATED = {
    "profile": {"present": True, "validated": True, "tier": "validated"},
    "email": {"present": True, "validated": False, "tier": "present"},
    "phone": {"present": True, "validated": True, "tier": "validated"},
    "address": {"present": True, "validated": True, "tier": "validated"},
    "website": {"present": True, "validated": True, "tier": "validated"},
    "freshness": {"present": True, "validated": True, "tier": "validated"},
}

EMAIL_ONLY_VALIDATED = {
    "profile": {"present": True, "validated": True, "tier": "validated"},
    "email": {"present": True, "validated": True, "tier": "validated"},
    "phone": {"present": True, "validated": False, "tier": "present"},
    "address": {"present": True, "validated": True, "tier": "validated"},
    "website": {"present": True, "validated": True, "tier": "validated"},
    "freshness": {"present": True, "validated": True, "tier": "validated"},
}


def phone_validated_json() -> str:
    """Profile present + phone tier validated. Clears baseline (phone is a business_contact) AND utilities."""
    return json.dumps(PHONE_VALIDATED)


def email_only_validated_json() -> str:
    """Profile present + email tier validated, phone tier below validated.
    Clears baseline (email is a business_contact) but NOT utilities (requires validated phone)."""
    return json.dumps(EMAIL_ONLY_VALIDATED)
