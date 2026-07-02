from __future__ import annotations
from app.quality.profiles.base import QualityProfile

UTILITIES = QualityProfile(
    key="utilities",
    label="Utilities (validated phone)",
    required={"profile": "present", "phone": "validated"},
    weights={},
)
