"""Sequential unattended bulk imports — operator tool for multi-region coverage runs.

Runs regions one at a time through the SAME pipeline as the admin bulk-import job
(run_bulk_import: dedup / opt-out / validation / provenance / ODbL attribution),
writing durable IngestionJob rows so the admin page shows the same honest funnels.

Usage (run with the app server STOPPED — one writer at a time):
    python scripts/import_regions.py wales scotland england

Progress prints to stdout (redirect to a log for long runs). Idempotent: re-running
a region merges instead of duplicating, so an interrupted run can simply be
restarted with the remaining regions.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Register ALL model tables before init_db (mirrors app/leadvault.py)
import app.campaigns.models  # noqa: F401
import app.fingerprints.models  # noqa: F401
import app.geo.ref  # noqa: F401
from sqlmodel import Session

from app.adapters.geofabrik import REGIONS
from app.core.db import IngestionJob, init_db
from app.ingestion.bulk import run_bulk_import


def _write_job(engine, job_id: int, status: str, counts: dict) -> None:
    with Session(engine) as s:
        row = s.get(IngestionJob, job_id)
        merged = dict(json.loads(row.counts_json or "{}"))
        merged.update(counts or {})
        row.status = status
        row.counts_json = json.dumps(merged)
        s.add(row)
        s.commit()


def main(regions: list[str]) -> int:
    unknown = [r for r in regions if r not in REGIONS]
    if unknown:
        print(f"unknown regions: {unknown}; known: {sorted(REGIONS)}")
        return 2
    engine = init_db(os.getenv("LEADVAULT_DB", "sqlite:///leadvault.db"))
    for region in regions:
        t0 = time.time()
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] START {region}", flush=True)
        with Session(engine) as s:
            job = IngestionJob(adapter_key="osm_geofabrik",
                               query_json=json.dumps({"region": region}),
                               status="running",
                               counts_json=json.dumps({"phase": "downloading"}))
            s.add(job)
            s.commit()
            s.refresh(job)
            job_id = job.id
        try:
            with Session(engine) as s:
                counts = run_bulk_import(
                    s, region,
                    on_progress=lambda c: _write_job(engine, job_id, "running", c),
                    on_phase=lambda p: _write_job(engine, job_id, "running", {"phase": p}),
                )
            _write_job(engine, job_id, "done", counts)
            mins = (time.time() - t0) / 60
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] DONE {region} in {mins:.0f}m "
                  f"{json.dumps(counts)}", flush=True)
        except BaseException as exc:  # noqa: BLE001 - job boundary; status must land
            _write_job(engine, job_id, "failed", {"error": str(exc)})
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] FAILED {region}: {exc}", flush=True)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
    print("ALL REGIONS COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or []))
