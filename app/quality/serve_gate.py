from __future__ import annotations

from app.core.targeting.view import lead_view
from app.quality.gate import clears_gate
from app.quality.profiles.baseline import BASELINE

_active = BASELINE


def set_gate_profile(profile) -> None:
    global _active
    _active = profile


def quality_serve_filter(session, buyer_account_id, lead) -> bool:
    return clears_gate(lead_view(lead), _active)
