from __future__ import annotations

from app.core.serve_filters import register_serve_filter
from app.quality.serve_gate import quality_serve_filter
from app.quality.profiles.registry import register
from app.quality.profiles.baseline import BASELINE
from app.quality.profiles.utilities import UTILITIES
from app.quality.profiles.generic import PHONE_VALIDATED, EMAIL_VALIDATED, CONTACT_VALIDATED


def register_quality_runtime() -> None:
    register_serve_filter(quality_serve_filter)
    register(BASELINE)
    register(UTILITIES)
    register(PHONE_VALIDATED)
    register(EMAIL_VALIDATED)
    register(CONTACT_VALIDATED)
