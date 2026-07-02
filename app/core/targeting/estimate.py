from __future__ import annotations

from datetime import datetime, timezone

from app.core.masking import mask_preview
from app.core.retention import is_expired
from app.core.compliance import lead_opted_out
from app.core.marketplace import _not_suppressed
from app.core.serve_filters import passes_serve_filters
from app.core.targeting.composition import matching_by_composition


def _days(iso):
    if not iso:
        return 1e9
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return 1e9
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0


def _score_band(v):
    return "0-49" if v < 50 else "50-69" if v < 70 else "70-84" if v < 85 else "85-100"


def _fresh_band(d):
    return "<=7" if d <= 7 else "<=30" if d <= 30 else "<=90" if d <= 90 else "older"


def estimate(session, buyer_account_id, composition, *, sample: int = 8, ctx=None) -> dict:
    leads = matching_by_composition(session, composition)
    visible = [l for l in leads
               if not is_expired(l)
               and not lead_opted_out(session, l)
               and _not_suppressed(session, buyer_account_id, l)
               and passes_serve_filters(session, buyer_account_id, l, ctx)]
    sd = {"0-49": 0, "50-69": 0, "70-84": 0, "85-100": 0}
    fd = {"<=7": 0, "<=30": 0, "<=90": 0, "older": 0}
    for l in visible:
        sd[_score_band(l.score_total)] += 1
        fd[_fresh_band(_days(l.date_last_verified))] += 1
    return {"count": len(visible), "score_distribution": sd,
            "freshness_distribution": fd,
            "samples": [mask_preview(l) for l in visible[:sample]]}
