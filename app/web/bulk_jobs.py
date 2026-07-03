"""One-at-a-time background bulk-import job (thread + IngestionJob row).

The web request only starts/polls/cancels; the thread owns its own Session.
Progress is durable (counts_json on the job row) so a page reload never loses
the funnel numbers.

Monkeypatch note: tests patch `app.web.bulk_jobs.run_bulk_import` at the
module level.  Inside _work(), referencing `run_bulk_import` as a bare name
resolves it through the module globals dict at CALL TIME (Python global lookup
is always dynamic), so the patch is visible to the thread without any extra
indirection.
"""
from __future__ import annotations

import json
import threading

from sqlmodel import Session, select

from app.core.db import IngestionJob
from app.ingestion.bulk import run_bulk_import  # patched by tests via monkeypatch

_lock = threading.Lock()
_state: dict = {"thread": None, "job_id": None, "cancel": False}


def active_job(session) -> IngestionJob | None:
    """Return the most-recent osm_geofabrik IngestionJob row, or None."""
    return session.exec(
        select(IngestionJob)
        .where(IngestionJob.adapter_key == "osm_geofabrik")
        .order_by(IngestionJob.id.desc())
    ).first()


def request_cancel(job_id: int | None = None) -> None:
    """Signal the running thread to stop after the current batch."""
    _state["cancel"] = True


def start_bulk_job(
    engine,
    region_key: str,
    scoring_profile_key: str,
    actor_user_id,
    run_fn=None,
) -> int:
    """Start a background bulk import.  Raises RuntimeError if one is already running.

    Args:
        engine: SQLAlchemy engine (thread will open its own Session).
        region_key: Key from REGIONS (e.g. "monaco", "great-britain").
        scoring_profile_key: Passed through to run_bulk_import; empty = no scoring.
        actor_user_id: User ID for the audit log.
        run_fn: Override the import function (used only by direct unit tests; the
                web routes never pass this — they rely on the monkeypatched module attr).

    Returns:
        The new IngestionJob.id.
    """
    with _lock:
        t = _state["thread"]
        if t is not None and t.is_alive():
            raise RuntimeError("a bulk import is already running")

        with Session(engine) as s:
            job = IngestionJob(
                adapter_key="osm_geofabrik",
                query_json=json.dumps({"region": region_key}),
                status="running",
                counts_json="{}",
            )
            s.add(job)
            s.commit()
            s.refresh(job)
            job_id = job.id

        _state["cancel"] = False
        _state["job_id"] = job_id

        def _work() -> None:
            # run_bulk_import is a MODULE GLOBAL — looked up from globals() at
            # call time, so monkeypatch(bj, "run_bulk_import", fake) takes effect.
            fn = run_fn or run_bulk_import  # noqa: F821 — intentional global lookup

            def _write(status: str, counts: dict) -> None:
                with Session(engine) as ws:
                    row = ws.get(IngestionJob, job_id)
                    if row is not None:
                        row.status = status
                        row.counts_json = json.dumps(counts)
                        ws.add(row)
                        ws.commit()

            try:
                with Session(engine) as ws:
                    counts = fn(
                        ws,
                        region_key,
                        scoring_profile_key=scoring_profile_key,
                        cancel_check=lambda: _state["cancel"],
                        on_progress=lambda c: _write("running", c),
                        actor_user_id=actor_user_id,
                    )
                final_status = "cancelled" if _state["cancel"] else "done"
                _write(final_status, counts)
            except Exception as exc:  # noqa: BLE001 — job boundary; surface via counts
                _write("failed", {"error": str(exc)})

        th = threading.Thread(target=_work, daemon=True)
        _state["thread"] = th
        th.start()
        return job_id
