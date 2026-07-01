from __future__ import annotations
from app.quality.profiles.base import QualityProfile

# "business_contact" is a virtual requirement satisfied by phone OR email at the tier.
BASELINE = QualityProfile(key="baseline", label="Baseline hot bar",
                          required={"profile": "present", "business_contact": "validated"},
                          weights={"profile": 30, "business_contact": 40, "address": 15,
                                   "website": 15})
