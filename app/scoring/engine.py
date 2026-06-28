from __future__ import annotations

from datetime import datetime, timezone


def _days_since(iso: str | None) -> float:
    if not iso:
        return 9999.0
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return 9999.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0


def generic_subscores(lead: dict) -> dict:
    contact_fields = [lead.get("phone"), lead.get("public_email"), lead.get("website_url")]
    present = sum(1 for f in contact_fields if f)
    contactability = round(present / 3 * 100)

    days = _days_since(lead.get("date_last_verified"))
    if days <= 7:
        freshness = 100
    elif days <= 30:
        freshness = 80
    elif days <= 90:
        freshness = 50
    elif days < 9999:
        freshness = 25
    else:
        freshness = 0

    confidence = round(min(100, int(lead.get("source_confidence", 50))))
    completeness = round(present / 3 * 100)
    clear = (lead.get("opt_out_status", "clear") == "clear"
             and lead.get("suppression_status", "clear") == "clear")
    compliance = 100 if clear else 0
    return {"contactability": contactability, "freshness": freshness,
            "confidence": confidence, "completeness": completeness,
            "compliance": compliance}


def score(lead: dict, profile) -> dict:
    base = generic_subscores(lead)
    return profile.combine(lead, base)
