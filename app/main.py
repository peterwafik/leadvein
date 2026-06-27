from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import (FileResponse, StreamingResponse, Response,
                               JSONResponse)
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.db import init_db, seed_builtins, all_recipes, Recipe
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


def _recipe_dict(recipe_id: str) -> dict | None:
    with Session(engine) as s:
        r = s.get(Recipe, recipe_id)
        if not r:
            return None
        return {
            "id": r.id, "category": r.category, "type": r.type,
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


@app.post("/api/recipes")
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


@app.post("/api/recipes/test")
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
                    "rows": [], "status": "pending", "totals": {}}
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
        # run_job defaults discover_fn to discover_meta (real network); when the
        # job carries manual_hosts, discovery is bypassed entirely.
        try:
            async for ev in run_job(job["recipe"], job["config"],
                                    fetch_fn=fetch_fn):
                if ev["type"] == "lead":
                    job["rows"].append(ev["lead"])
                if ev["type"] == "done":
                    job["status"] = "done"
                    job["totals"] = ev["totals"]
                yield f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n"
        except Exception as e:  # surface engine errors to the client
            job["status"] = "error"
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _job_rows(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@app.get("/api/jobs/{job_id}/results.csv")
def results_csv(job_id: str):
    job = _job_rows(job_id)
    data = rows_to_csv(job["columns"], job["rows"])
    return Response(content=data, media_type="text/csv",
                    headers={"Content-Disposition":
                             f'attachment; filename="leads_{job_id}.csv"'})


@app.get("/api/jobs/{job_id}/results.xlsx")
def results_xlsx(job_id: str):
    job = _job_rows(job_id)
    sheet = f"{job['recipe'].type} Prospects"
    data = rows_to_xlsx(sheet, job["columns"], job["rows"])
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="leads_{job_id}.xlsx"'})


@app.post("/api/jobs/{job_id}/append")
async def append_tracker(job_id: str, file: UploadFile = File(...)):
    job = _job_rows(job_id)
    existing = await file.read()
    sheet = f"{job['recipe'].type} Prospects"
    merged = append_xlsx(existing, sheet, job["rows"])
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
