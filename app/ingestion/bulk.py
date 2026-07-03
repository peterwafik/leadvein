"""Bulk import driver: Geofabrik PBF -> batched pipeline (spec §1.3).

Reuses the SAME contracts as every other source: dedupe_key, opt-out check,
build_validation (single validation authority), scoring, per-field provenance
via merge_or_create. Deliberately NO per-lead website enrichment (a national
run would mean 300k network fetches) — enrichment stays a separate targeted
admin pass. MX lookups are cached per unique domain for the run.

NOTE on parse vs. import cancellation: stream_business_leads buffers all
matching leads internally (apply_file completes before first yield). The
cancel_check between yields therefore stops IMPORTING promptly but cannot
stop PARSING. This is acceptable because parsing is the cheap half of the
work; the large wall-clock cost is the network download and DB writes.

NOTE on ``hot`` semantics: ``hot`` counts every lead TOUCHED this run whose
post-merge tier_contact >= "validated".  A re-import will count already-hot
merged leads again.  It is NOT "leads made hot by this run".
"""
from __future__ import annotations

from app.adapters.geofabrik import GEOFABRIK, REGIONS, download_extract
from app.core.compliance import audit, host_of, is_opted_out
from app.core.dedup import dedupe_key, find_existing
from app.core.targeting.coverage import recompute_coverage
from app.geo.coverage import invalidate_geo_counts
from app.ingestion.pbf_stream import stream_business_leads
from app.ingestion.pipeline import merge_or_create
from app.quality.ordinals import ordinal
from app.quality.validators.email import _default_mx


def _cached_mx():
    """Return a per-run MX lookup that caches DNS results by domain.

    _default_mx(domain: str) -> bool — verified signature in
    app/quality/validators/email.py. The cache wrapper matches that exact
    signature so it can be passed as mx_lookup to build_validation.
    """
    cache: dict[str, bool] = {}

    def lookup(domain: str) -> bool:
        if domain not in cache:
            cache[domain] = _default_mx(domain)
        return cache[domain]

    return lookup


def run_bulk_import(
    session,
    region_key: str,
    *,
    scoring_profile_key: str = "",
    pbf_path: str | None = None,
    batch_size: int = 500,
    cancel_check=None,
    on_progress=None,
    on_phase=None,
    actor_user_id=None,
) -> dict:
    """Import business leads from a Geofabrik PBF extract into the DB.

    Args:
        session: SQLModel/SQLAlchemy session.
        region_key: Key in REGIONS (e.g. "monaco", "great-britain").
        scoring_profile_key: Optional scoring profile; empty = no scoring.
        pbf_path: Override PBF path (used by tests/fixtures to skip download).
        batch_size: Leads per commit batch (tune for memory vs. durability).
        cancel_check: Callable() -> bool; truthy between batches stops the run
            cleanly. Committed batches stay; any pending batch is abandoned.
        on_progress: Callable(counts_dict) called after each committed batch.
        on_phase: Optional Callable(phase: str) invoked when the import enters
            a new phase: "parsing" (PBF is downloaded, starting element scan)
            and "importing" (first batch flush beginning). Used by the background
            job to update the status block without waiting for the first
            on_progress call.
        actor_user_id: User ID for the audit log entry (None = system).

    Returns:
        dict with keys: elements_seen, matched, stored_new, merged,
        skipped_compliance, skipped_duplicate_in_run, hot.
    """
    region = REGIONS[region_key]
    counts = {
        "elements_seen": 0,
        "matched": 0,
        "stored_new": 0,
        "merged": 0,
        "skipped_compliance": 0,
        "skipped_duplicate_in_run": 0,
        # hot: leads TOUCHED this run with tier_contact >= "validated".
        # A re-import recounts already-hot merged leads; not "made hot this run".
        "hot": 0,
    }

    path = pbf_path or download_extract(region_key)

    # Signal "parsing" phase now that download is complete.
    if on_phase:
        on_phase("parsing")

    mx = _cached_mx()
    seen_keys: set[str] = set()
    batch: list = []
    _first_flush = True

    def _progress(n_elements: int) -> None:
        counts["elements_seen"] = n_elements

    def _flush() -> None:
        nonlocal _first_flush
        from app.core.leadcats import sync_lead_categories

        # Signal "importing" on the very first flush so the UI updates before
        # any on_progress callback fires (first flush has no prior progress call).
        if _first_flush:
            _first_flush = False
            if on_phase:
                on_phase("importing")

        for n in batch:
            domain = host_of(n.website_url)
            if is_opted_out(session, domain=domain, phone=n.phone,
                            email=n.public_email):
                counts["skipped_compliance"] += 1
                continue

            # Authoritative new-vs-merged detection: query BEFORE merge_or_create.
            # (merge_or_create also calls find_existing internally; this pre-check
            # adds one indexed query per lead but avoids unreliable session.new
            # heuristics and is the controller-approved approach.)
            key = dedupe_key(n)
            is_new = find_existing(session, key) is None

            lead = merge_or_create(
                session, n,
                source_key=GEOFABRIK.meta.key,
                license=GEOFABRIK.meta.license,
                scoring_profile_key=scoring_profile_key,
                attribution=GEOFABRIK.attribution(),
                source_name=GEOFABRIK.meta.name,
                source_url=GEOFABRIK.meta.url,
                enrichment={},
                country_override=region["country"],
                mx_lookup=mx,
            )

            if is_new:
                counts["stored_new"] += 1
                sync_lead_categories(session, lead)
            else:
                counts["merged"] += 1

            # "hot" = POST-merge tier_contact >= ordinal("validated")
            if lead.tier_contact >= ordinal("validated"):
                counts["hot"] += 1

        session.commit()
        batch.clear()
        if on_progress:
            on_progress(dict(counts))

    node_cache = None
    if pbf_path is None:          # real extract: file-backed node location index
        import os
        node_cache = os.path.join("var", "pbf", f"{region_key}-nodes.cache")

    for n in stream_business_leads(
        path,
        source_key=GEOFABRIK.meta.key,
        node_cache_path=node_cache,
        progress_cb=_progress,
    ):
        if cancel_check and cancel_check():
            break
        counts["matched"] += 1
        key = dedupe_key(n)
        if key in seen_keys:
            counts["skipped_duplicate_in_run"] += 1
            continue
        seen_keys.add(key)
        batch.append(n)
        if len(batch) >= batch_size:
            _flush()

    # Flush remaining batch only if not cancelled
    if batch and not (cancel_check and cancel_check()):
        _flush()

    recompute_coverage(session)
    invalidate_geo_counts()
    audit(session, actor_user_id, "bulk_ingest", "IngestionJob", region_key, counts)
    session.commit()

    # Clean up file-backed node cache
    if node_cache:
        import os
        try:
            os.remove(node_cache)
        except OSError:
            pass

    return counts
