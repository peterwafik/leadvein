from __future__ import annotations


def validate_website(intent: dict) -> dict:
    reachable = bool((intent or {}).get("website_reachable"))
    return {"present": reachable or bool((intent or {}).get("last_scanned")),
            "validated": reachable}
