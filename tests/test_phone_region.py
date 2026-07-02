"""Tests that phone-validation region is derived from the lead's country field.

validate_phone returns: {"present": bool, "validated": bool, "line_type": str}
build_validation adds:  {"tier": str}  via achieved_tier()

NOTE: phonenumbers ignores the region hint for E.164/international numbers that
start with '+', because the dialling prefix already encodes the country.  Region
only matters for *local-format* numbers (no '+').  We therefore use a local US
number to demonstrate that the region derivation actually changes the outcome.
"""
from app.quality.stamp import build_validation


def test_phone_region_derived_from_country():
    # Local-format US number — region matters here (no '+' prefix).
    local_us = "415-555-0132"

    # Parsed as GB (wrong region) → should not be a valid GB number.
    as_gb = build_validation({"phone": local_us, "country": "GB"})
    assert as_gb["phone"]["validated"] is False, (
        f"local US number must be invalid when region is GB, got: {as_gb['phone']}")

    # Parsed as US (correct region derived from country) → valid.
    as_us = build_validation({"phone": local_us, "country": "US"})
    assert as_us["phone"]["validated"] is True, (
        f"local US number must be valid when region is US, got: {as_us['phone']}")
    assert as_us["phone"]["tier"] in ("validated", "present"), (
        f"tier must be 'validated' or 'present' for a valid US number, got: {as_us['phone']['tier']}")

    # A GB number still validates as GB (no regression).
    gbnum = build_validation({"phone": "020 7946 0018", "country": "GB"})
    assert gbnum["phone"]["validated"] is True, (
        f"020 number must be valid under GB region, got: {gbnum['phone']}")

    # Unknown / empty country falls back to the configurable default (GB).
    dflt = build_validation({"phone": "020 7946 0018", "country": ""})
    assert dflt["phone"]["validated"] is True, (
        f"020 number must be valid when country is empty (falls back to default GB), got: {dflt['phone']}")

    # Multi-word / non-2-letter country string also falls back to default.
    long_name = build_validation({"phone": "020 7946 0018", "country": "United Kingdom"})
    assert long_name["phone"]["validated"] is True, (
        f"020 number must be valid when country is a long name (falls back to default GB), got: {long_name['phone']}")
