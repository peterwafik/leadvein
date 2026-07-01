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
