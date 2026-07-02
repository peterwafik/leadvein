from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlmodel import Session, select

from app.core.db import IngestRequest
from app.geo.coverage import geo_lead_counts
from app.geo.ref import list_countries, search_areas
from app.web.csrf import csrf_protect_json
from app.web.deps import get_session, current_user, redirect

router = APIRouter(prefix="/app/geo")


def _authed(request: Request, session: Session):
    u = current_user(request, session)
    return u if u and u.role in ("buyer", "admin") else None


@router.get("/countries")
def countries(request: Request, session: Session = Depends(get_session)):
    if not _authed(request, session):
        return redirect("/login")
    counts = geo_lead_counts(session)["countries"]
    return JSONResponse({"countries": [
        {"code": c.country_code, "name": c.country_name,
         "lead_count": counts.get(c.country_code, 0)}
        for c in list_countries(session)]})


@router.get("/areas")
def areas(request: Request, country: str = "", q: str = "",
          session: Session = Depends(get_session)):
    if not _authed(request, session):
        return redirect("/login")
    cc = (country or "").upper()
    counts = geo_lead_counts(session)
    groups: dict[str, list] = {}
    matched_lower: set[str] = set()
    for row in search_areas(session, cc, q):
        if row.kind == "city":
            n = counts["cities"].get((cc, row.ascii_name.lower()), 0) \
                or counts["cities"].get((cc, row.name.lower()), 0)
            matched_lower.add(row.ascii_name.lower()); matched_lower.add(row.name.lower())
        else:
            n = counts["regions"].get((cc, row.ascii_name.lower()), 0) \
                or counts["regions"].get((cc, row.name.lower()), 0)
        label = " · ".join(x for x in (row.admin1_name, row.admin2_name) if x) \
                or row.country_name
        groups.setdefault(label, []).append(
            {"name": row.name, "kind": row.kind, "lead_count": n,
             "_pop": row.population})
    out_groups = []
    for label, areas_ in groups.items():
        areas_.sort(key=lambda a: (-a["lead_count"], -a.pop("_pop")))
        out_groups.append({"label": label, "areas": areas_})
    out_groups.sort(key=lambda g: -max((a["lead_count"] for a in g["areas"]), default=0))
    # Inventory cities in this country that the reference doesn't know — never hide
    ql = (q or "").strip().lower()
    other = [{"name": counts["city_names"][cl], "lead_count": n}
             for (ccc, cl), n in counts["cities"].items()
             if ccc == cc and cl not in matched_lower
             and (not ql or ql in cl)]
    other.sort(key=lambda a: -a["lead_count"])
    return JSONResponse({"groups": out_groups, "other": other})


@router.post("/ingest-request", dependencies=[Depends(csrf_protect_json)])
async def ingest_request(request: Request, session: Session = Depends(get_session)):
    u = _authed(request, session)
    if not u:
        return Response(status_code=401)
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=400)
    country = (body.get("country") or "").upper().strip()
    area = (body.get("area") or "").strip()
    if not area:
        return Response(status_code=400)
    dup = session.exec(select(IngestRequest).where(
        IngestRequest.country == country, IngestRequest.area == area,
        IngestRequest.status == "open")).first()
    if not dup:
        session.add(IngestRequest(country=country, area=area, requested_by=u.id))
        session.commit()
    return JSONResponse({"status": "requested"})
