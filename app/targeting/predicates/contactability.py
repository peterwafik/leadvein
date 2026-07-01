from __future__ import annotations
from app.core.targeting.view import get_path, MISSING

ROLE_PREFIXES = {"info", "sales", "support", "hello", "contact", "enquiries",
                 "enquiry", "admin", "office", "accounts", "bookings", "help"}


def _local(email: str) -> str:
    return (email or "").split("@", 1)[0].strip().lower()


class _HasPhone:
    key = "contactability.has_phone"; group = "contactability"; label = "Has phone"
    reads = ["phone"]; params_schema = {}
    def matches(self, view, params):
        val = get_path(view, "phone")
        if val is MISSING:
            return None
        return bool(val)


class _HasRoleEmail:   # INV-2: business-role local-part allowlist ONLY
    key = "contactability.has_role_email"; group = "contactability"; label = "Has role-based email"
    reads = ["public_email"]; params_schema = {}
    def matches(self, view, params):
        val = get_path(view, "public_email")
        if val is MISSING:   # truly-absent path -> unknown; empty string -> known "no role email" (False)
            return None
        return _local(val) in ROLE_PREFIXES


class _HasBusinessContact:
    key = "contactability.has_business_contact"; group = "contactability"; label = "Has business contact"
    reads = ["phone", "public_email"]; params_schema = {}
    def matches(self, view, params):
        phone = get_path(view, "phone"); email = get_path(view, "public_email")
        has_phone = bool(phone) if phone is not MISSING else False
        has_role = (_local(email) in ROLE_PREFIXES) if (email is not MISSING and email) else False
        if has_phone or has_role:
            return True
        # neither present-and-usable: if both fields absent -> unknown; else known-False
        if phone is MISSING and (email is MISSING or not email):
            return None
        return False


HAS_PHONE = _HasPhone(); HAS_ROLE_EMAIL = _HasRoleEmail(); HAS_BUSINESS_CONTACT = _HasBusinessContact()
