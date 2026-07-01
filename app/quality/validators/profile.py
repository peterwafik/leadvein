from __future__ import annotations


def validate_profile(name="", category_keys=None, city="", opening_hours="", website_url="") -> dict:
    cats = category_keys or []
    present = bool(name)
    validated = bool(name) and bool(cats) and bool(city)
    return {"present": present, "validated": validated}
