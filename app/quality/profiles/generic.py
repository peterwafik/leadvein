"""Generic contact-channel profiles the campaign builder maps plain answers onto.
Self-run validation caps at "validated" (INV-Q2) — these never require verified_live."""
from __future__ import annotations

from app.quality.profiles.base import QualityProfile

PHONE_VALIDATED = QualityProfile(
    key="phone_validated", label="Validated phone",
    required={"profile": "present", "phone": "validated"})

EMAIL_VALIDATED = QualityProfile(
    key="email_validated", label="Validated email",
    required={"profile": "present", "email": "validated"})

CONTACT_VALIDATED = QualityProfile(
    key="contact_validated", label="Any validated contact",
    required={"profile": "present", "business_contact": "validated"})
