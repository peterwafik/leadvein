from __future__ import annotations
from datetime import datetime, timezone


def validate_freshness(date_last_verified, *, fresh_days: int = 90) -> dict:
    if not date_last_verified:
        return {"present": False, "validated": False}
    try:
        dt = datetime.fromisoformat(date_last_verified)
    except ValueError:
        return {"present": False, "validated": False}
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    return {"present": True, "validated": days <= fresh_days}
