from __future__ import annotations
from sqlmodel import Session, select, delete
from app.core.db import Lead, AttributeCoverage, _now
from app.core.targeting import registry
from app.core.targeting.view import lead_view, get_path, MISSING


def TRACKED_PATHS() -> list[str]:
    paths = set()
    for k in registry.all_keys():
        paths.update(registry.get(k).reads)
    return sorted(paths)


def _populated(view, path) -> bool:
    v = get_path(view, path)
    return v is not MISSING and v not in (None, "", [], {})


def recompute_coverage(session: Session) -> int:
    leads = session.exec(select(Lead)).all()
    total = len(leads)
    paths = TRACKED_PATHS()
    counts = {p: 0 for p in paths}
    for l in leads:
        v = lead_view(l)
        for p in paths:
            if _populated(v, p):
                counts[p] += 1
    session.exec(delete(AttributeCoverage))
    for p, n in counts.items():
        session.add(AttributeCoverage(path=p, populated=n, total=total, updated_at=_now()))
    session.commit()
    return len(paths)


def populated_paths(session: Session, min_count: int = 1) -> set:
    return {r.path for r in session.exec(select(AttributeCoverage).where(
        AttributeCoverage.populated >= min_count)).all()}


def coverage_pct(session: Session, path: str) -> float:
    r = session.exec(select(AttributeCoverage).where(AttributeCoverage.path == path)).first()
    if not r or not r.total:
        return 0.0
    return round(r.populated / r.total * 100, 1)
