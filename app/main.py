from __future__ import annotations

import base64
import json
import os
import secrets
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import (FileResponse, StreamingResponse, Response,
                               JSONResponse)
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from app.db import init_db, seed_builtins, all_recipes, Recipe, Job, Lead
from app.engine.discover import discover
from app.engine.enrich import fetch, analyse, norm_url
from app.engine.export import rows_to_csv, rows_to_xlsx, append_xlsx
from app.engine.runner import run_job, JobConfig
from app.schemas import (RecipeCreate, TestRecipeRequest, JobCreate,
                         engine_recipe_from_api, DEFAULT_COLUMNS)

load_dotenv()
STATIC_DIR = Path(__file__).parent / "static"
URLSCAN_KEY = os.getenv("URLSCAN_KEY") or None
PUBLICWWW_KEY = os.getenv("PUBLICWWW_KEY") or None

app = FastAPI(title="Lead Scraper")
engine = init_db()
with Session(engine) as _s:
    seed_builtins(_s)

JOBS: dict[str, dict] = {}
FETCH_OVERRIDE = None  # tests may set this to bypass network


# --- admin auth (opt-in) ----------------------------------------------------
# Recipe management (create/test) is gated behind a single admin login whose
# credentials come from the environment (ADMIN_USER / ADMIN_PASSWORD), never
# hardcoded. If ADMIN_PASSWORD is unset/empty the app runs OPEN (local default)
# and admin routes are ungated. Running jobs + downloading exports are NEVER
# gated — unauthenticated users are "run-only". Read at request time so the
# mode can change without a restart (and so tests can set it via env).
def require_admin(request: Request) -> None:
    password = os.getenv("ADMIN_PASSWORD") or ""
    if not password:
        return  # auth disabled — open/local mode
    user = os.getenv("ADMIN_USER") or "admin"
    header = request.headers.get("Authorization", "")
    if header.startswith("Basic "):
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
            u, _, p = decoded.partition(":")
        except Exception:
            u = p = ""
        if secrets.compare_digest(u, user) and secrets.compare_digest(p, password):
            return
    raise HTTPException(status_code=401, detail="admin authentication required",
                        headers={"WWW-Authenticate": "Basic"})


def _recipe_dict(recipe_id: str) -> dict | None:
    with Session(engine) as s:
        r = s.get(Recipe, recipe_id)
        if not r:
            return None
        return {
            "id": r.id, "category": r.category, "type": r.type, "logo": r.logo,
            "urlscan_query": r.urlscan_query, "publicwww_query": r.publicwww_query,
            "verify_fingerprints": json.loads(r.fingerprints_json or "[]"),
            "id_extractors": json.loads(r.extractors_json or "{}"),
            "exclude_hosts": json.loads(r.exclude_hosts_json or "[]"),
            "is_builtin": r.is_builtin,
        }


@app.get("/api/recipes")
def list_recipes():
    with Session(engine) as s:
        recipes = all_recipes(s)
    grouped: dict[str, list] = {}
    for r in recipes:
        grouped.setdefault(r["category"], []).append(r)
    return {"recipes": recipes, "grouped": grouped}


@app.post("/api/recipes", dependencies=[Depends(require_admin)])
def create_recipe(body: RecipeCreate):
    rid = body.type.lower().replace(" ", "_") + "_" + uuid.uuid4().hex[:6]
    with Session(engine) as s:
        s.add(Recipe(
            id=rid, category=body.category, type=body.type,
            urlscan_query=body.urlscan_query, publicwww_query=body.publicwww_query,
            fingerprints_json=json.dumps(body.verify_fingerprints),
            extractors_json=json.dumps(body.id_extractors),
            exclude_hosts_json=json.dumps(body.exclude_hosts),
            is_builtin=False,
        ))
        s.commit()
    return _recipe_dict(rid)


@app.post("/api/recipes/test", dependencies=[Depends(require_admin)])
def test_recipe(body: TestRecipeRequest):
    recipe = engine_recipe_from_api(body.model_dump())
    try:
        hosts = discover(recipe, source=body.source, limit=5,
                         urlscan_key=URLSCAN_KEY, publicwww_key=PUBLICWWW_KEY)
    except Exception as e:
        raise HTTPException(400, f"Discovery failed: {e}")
    fetch_fn = FETCH_OVERRIDE or fetch
    samples = []
    matched = 0
    for h in hosts:
        try:
            final_url, html = fetch_fn(norm_url(h))
            if not html:
                samples.append({"host": h, "confirmed": False, "matched": ""})
                continue
            lead = analyse(recipe, final_url or h, html)
            if lead.on_platform:
                matched += 1
            samples.append({"host": h, "confirmed": lead.on_platform,
                            "matched": lead.matched})
        except Exception as e:
            samples.append({"host": h, "confirmed": False, "matched": "",
                            "error": str(e)})
    return {"checked": len(hosts), "matched": matched, "samples": samples}


@app.post("/api/jobs")
def create_job(body: JobCreate):
    rd = _recipe_dict(body.recipe_id)
    if not rd:
        raise HTTPException(404, "recipe not found")
    recipe = engine_recipe_from_api(rd)
    columns = body.columns or list(DEFAULT_COLUMNS)
    config = JobConfig(
        source=body.source, limit=min(body.limit, 1000), keyword=body.keyword,
        country=body.country, delay=body.delay,
        concurrency=min(body.concurrency, 10), only_confirmed=body.only_confirmed,
        urlscan_key=URLSCAN_KEY, publicwww_key=PUBLICWWW_KEY,
        manual_hosts=[h.strip() for h in body.manual_hosts if h.strip()],
    )
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"recipe": recipe, "config": config, "columns": columns,
                    "status": "pending", "totals": {}}
    filters = {"keyword": body.keyword, "country": body.country,
               "limit": config.limit, "delay": config.delay,
               "concurrency": config.concurrency,
               "only_confirmed": config.only_confirmed,
               "manual_hosts": len(config.manual_hosts)}
    with Session(engine) as s:
        s.add(Job(id=job_id, recipe_id=body.recipe_id, source=body.source,
                  filters_json=json.dumps(filters), columns_json=json.dumps(columns),
                  status="pending", totals_json="{}"))
        s.commit()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job["status"] != "pending":
        raise HTTPException(409, "job already started or completed")

    async def event_gen():
        job["status"] = "running"
        fetch_fn = FETCH_OVERRIDE or fetch
        _set_job_status(job_id, "running")
        # run_job defaults discover_fn to discover_meta (real network); when the
        # job carries manual_hosts, discovery is bypassed entirely. Leads are
        # persisted to the DB as they arrive, so results survive a restart.
        with Session(engine) as s:
            try:
                async for ev in run_job(job["recipe"], job["config"],
                                        fetch_fn=fetch_fn):
                    if ev["type"] == "lead":
                        s.add(_lead_from_row(job_id, ev["lead"]))
                        s.commit()
                    if ev["type"] == "done":
                        job["status"] = "done"
                        job["totals"] = ev["totals"]
                        _set_job_status(job_id, "done", ev["totals"], session=s)
                    yield f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n"
            except Exception as e:  # surface engine errors to the client
                job["status"] = "error"
                _set_job_status(job_id, "error", session=s)
                yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


_LEAD_FIELDS = ["name", "website", "on_platform", "matched", "email",
                "emails_all", "phone", "phones_all", "address", "country",
                "platform", "source_query", "status", "notes"]


def _lead_from_row(job_id: str, row: dict) -> Lead:
    # map the runner's column-keyed lead dict onto a Lead row (display strings
    # for ids/socials are stored in the *_json columns).
    return Lead(
        job_id=job_id,
        ids_json=row.get("ids", ""), socials_json=row.get("socials", ""),
        **{f: row.get(f, "") for f in _LEAD_FIELDS},
    )


def _lead_to_rowdict(l: Lead) -> dict:
    d = {f: getattr(l, f) for f in _LEAD_FIELDS}
    d["ids"] = l.ids_json
    d["socials"] = l.socials_json
    return d


def _set_job_status(job_id: str, status: str, totals: dict | None = None,
                    session: Session | None = None) -> None:
    own = session is None
    s = session or Session(engine)
    try:
        db_job = s.get(Job, job_id)
        if db_job:
            db_job.status = status
            if totals is not None:
                db_job.totals_json = json.dumps(totals)
            s.add(db_job)
            s.commit()
    finally:
        if own:
            s.close()


def _load_job_for_download(job_id: str):
    """Read a job's columns, sheet name, and lead rows from the DB."""
    with Session(engine) as s:
        db_job = s.get(Job, job_id)
        if not db_job:
            raise HTTPException(404, "job not found")
        columns = json.loads(db_job.columns_json or "[]") or list(DEFAULT_COLUMNS)
        rec = s.get(Recipe, db_job.recipe_id)
        sheet = f"{(rec.type if rec else 'Leads')} Prospects"
        leads = s.exec(select(Lead).where(Lead.job_id == job_id)
                       .order_by(Lead.id)).all()
        rows = [_lead_to_rowdict(l) for l in leads]
    return columns, sheet, rows


@app.get("/api/jobs")
def list_jobs():
    with Session(engine) as s:
        jobs = s.exec(select(Job).order_by(Job.created_at.desc())).all()
        recipe_types = {r.id: r.type for r in s.exec(select(Recipe)).all()}
        out = []
        for j in jobs:
            n = len(s.exec(select(Lead.id).where(Lead.job_id == j.id)).all())
            out.append({
                "id": j.id, "recipe_id": j.recipe_id,
                "type": recipe_types.get(j.recipe_id, j.recipe_id),
                "source": j.source, "status": j.status,
                "created_at": j.created_at,
                "totals": json.loads(j.totals_json or "{}"),
                "filters": json.loads(j.filters_json or "{}"),
                "lead_count": n,
            })
    return {"jobs": out}


@app.get("/api/jobs/{job_id}/results.csv")
def results_csv(job_id: str):
    columns, _sheet, rows = _load_job_for_download(job_id)
    data = rows_to_csv(columns, rows)
    return Response(content=data, media_type="text/csv",
                    headers={"Content-Disposition":
                             f'attachment; filename="leads_{job_id}.csv"'})


@app.get("/api/jobs/{job_id}/results.xlsx")
def results_xlsx(job_id: str):
    columns, sheet, rows = _load_job_for_download(job_id)
    data = rows_to_xlsx(sheet, columns, rows)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="leads_{job_id}.xlsx"'})


@app.post("/api/jobs/{job_id}/append")
async def append_tracker(job_id: str, file: UploadFile = File(...)):
    _columns, sheet, rows = _load_job_for_download(job_id)
    existing = await file.read()
    merged = append_xlsx(existing, sheet, rows)
    return Response(
        content=merged,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="tracker_{job_id}.xlsx"'})


# static + index (mounted last so /api/* wins)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    idx = STATIC_DIR / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return JSONResponse({"detail": "UI not built"}, status_code=200)
