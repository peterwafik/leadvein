from __future__ import annotations

from app.core.targeting.view import lead_view
from app.quality.gate import clears_gate
from app.quality.profiles.baseline import BASELINE

_active = BASELINE


def set_gate_profile(profile) -> None:
    global _active
    _active = profile


def quality_serve_filter(session, buyer_account_id, lead, ctx=None) -> bool:
    view = lead_view(lead)
    if not clears_gate(view, _active):
        return False
    prof = (ctx or {}).get("quality_profile")
    if prof is not None and not clears_gate(view, prof):
        return False
    return True
