from __future__ import annotations


def validate_address(line1="", city="", postal_code="", country="", lat=None, lon=None) -> dict:
    present = bool(line1 or city)
    geocoded = lat is not None and lon is not None   # offline: OSM node coords; NOT deliverability
    return {"present": present, "validated": present and geocoded, "geocoded": geocoded}
