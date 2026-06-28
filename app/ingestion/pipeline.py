from __future__ import annotations

import json

from sqlmodel import Session

from app.adapters.base import AdapterQuery, NormalizedLead
from app.core.compliance import host_of, is_opted_out, audit
from app.core.db import Lead, IngestionJob, _now
from app.core.dedup import dedupe_key, find_existing
from app.core.sources import ensure_source
from app.enrich.website import enrich_website
from app.scoring.engine import score
from app.scoring.profiles import registry as profile_registry


def _lead_context(n: NormalizedLead, enrichment: dict) -> dict:
    return {"category_keys": n.category_keys, "phone": n.phone,
            "public_email": n.public_email, "website_url": n.website_url,
            "attributes": {**n.attributes, **enrichment},
            "intent": enrichment, "date_last_verified": _now(),
            "source_confidence": 70, "opt_out_status": "clear",
            "suppression_status": "clear"}


def ingest(session: Session, adapter, query: AdapterQuery, *, scoring_profile_key: str,
           enrich_fn=enrich_website, actor_user_id=None) -> dict:
    ensure_source(session, adapter.meta)
    profile = profile_registry.get(scoring_profile_key)
    counts = {"discovered": 0, "normalized": 0, "stored": 0,
              "skipped_duplicate": 0, "skipped_compliance": 0}
    seen_in_run: set[str] = set()

    for raw in adapter.discover(query):
        counts["discovered"] += 1
        n = adapter.normalize(raw)
        if n is None:
            continue
        counts["normalized"] += 1
        key = dedupe_key(n)
        if key in seen_in_run or find_existing(session, key):
            counts["skipped_duplicate"] += 1
            continue
        seen_in_run.add(key)
        domain = host_of(n.website_url)
        if is_opted_out(session, domain=domain, phone=n.phone, email=n.public_email):
            counts["skipped_compliance"] += 1
            continue
        enrichment = enrich_fn(n)
        ctx = _lead_context(n, enrichment)
        scored = score(ctx, profile)
        addr = n.address or {}
        session.add(Lead(
            business_name=n.business_name,
            category_keys_json=json.dumps(n.category_keys),
            address_line1=addr.get("line1", ""), city=addr.get("city", ""),
            region=addr.get("region", ""), postal_code=addr.get("postal_code", ""),
            country=addr.get("country", ""), latitude=addr.get("lat"),
            longitude=addr.get("lon"), phone=n.phone, public_email=n.public_email,
            website_url=n.website_url,
            attributes_json=json.dumps({**n.attributes, **enrichment}),
            intent_json=json.dumps(enrichment),
            score_total=scored["total"], subscores_json=json.dumps(scored["subscores"]),
            score_explanation=scored["explanation"],
            scoring_profile_key=scoring_profile_key,
            source_key=n.source_key, source_name=adapter.meta.name,
            source_url=n.source_url or adapter.meta.url,
            source_license=n.source_license or adapter.meta.license,
            date_last_verified=_now(), dedupe_key=key))
        counts["stored"] += 1

    job = IngestionJob(adapter_key=adapter.meta.key,
                       query_json=json.dumps({"area": query.area,
                                              "categories": query.categories}),
                       status="done", counts_json=json.dumps(counts))
    session.add(job)
    session.commit()
    audit(session, actor_user_id, "ingest", "IngestionJob", str(job.id), counts)
    return counts
