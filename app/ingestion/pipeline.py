from __future__ import annotations

import json

from sqlmodel import Session

from app.adapters.base import AdapterQuery, NormalizedLead
from app.adapters.budget import stamp_provenance
from app.core.compliance import host_of, is_opted_out, audit
from app.core.db import Lead, IngestionJob, _now
from app.core.retention import expiry_for
from app.core.dedup import dedupe_key, find_existing, name_city_fallback_key
from app.core.sources import ensure_source
from app.core.targeting.coverage import recompute_coverage
from app.enrich.website import enrich_website
from app.scoring.engine import score
from app.scoring.profiles import registry as profile_registry
from app.quality.stamp import build_validation, quality_score
from app.quality.ordinals import apply_tier_columns


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
        _country = addr.get("country") or query.country or ""  # OSM tag wins, else pull context
        _val = build_validation({
            "email": n.public_email, "phone": n.phone,
            "country": _country,
            "address": {"line1": addr.get("line1", ""),
                        "city": addr.get("city", ""),
                        "postal_code": addr.get("postal_code", ""),
                        "country": _country,
                        "lat": addr.get("lat"), "lon": addr.get("lon")},
            "intent": enrichment, "name": n.business_name, "category_keys": n.category_keys,
            "city": addr.get("city", ""), "opening_hours": n.opening_hours,
            "website_url": n.website_url, "date_last_verified": _now()})
        lead_obj = Lead(
            business_name=n.business_name,
            category_keys_json=json.dumps(n.category_keys),
            address_line1=addr.get("line1", ""), city=addr.get("city", ""),
            region=addr.get("region", ""), postal_code=addr.get("postal_code", ""),
            country=_country, latitude=addr.get("lat"),
            longitude=addr.get("lon"), phone=n.phone, public_email=n.public_email,
            website_url=n.website_url,
            attributes_json=json.dumps({**n.attributes, **enrichment}),
            intent_json=json.dumps(enrichment),
            score_total=scored["total"], subscores_json=json.dumps(scored["subscores"]),
            score_explanation=scored["explanation"],
            scoring_profile_key=scoring_profile_key,
            source_key=n.source_key or adapter.meta.key, source_name=adapter.meta.name,
            source_url=n.source_url or adapter.meta.url,
            source_license=n.source_license or adapter.meta.license,
            attribution=adapter.attribution(),
            date_last_verified=_now(),
            retention_expiry=expiry_for(_now()),
            dedupe_key=key,
            validation_json=json.dumps(_val), completeness_score=quality_score(_val))
        apply_tier_columns(lead_obj, _val)
        session.add(lead_obj)
        session.flush()  # assign lead_obj.id
        from app.core.leadcats import sync_lead_categories
        sync_lead_categories(session, lead_obj)
        counts["stored"] += 1

    job = IngestionJob(adapter_key=adapter.meta.key,
                       query_json=json.dumps({"area": query.area,
                                              "categories": query.categories}),
                       status="done", counts_json=json.dumps(counts))
    session.add(job)
    session.commit()
    recompute_coverage(session)
    audit(session, actor_user_id, "ingest", "IngestionJob", str(job.id), counts)
    return counts


def merge_or_create(
    session: Session,
    normalized: NormalizedLead,
    *,
    source_key: str,
    license: str,  # noqa: A002
    scoring_profile=None,
    scoring_profile_key: str = "",
    attribution: str = "",
    source_name: str = "",
    source_url: str = "",
    enrichment: dict | None = None,
    country_override: str = "",
) -> Lead:
    """Find the matching Lead and gap-fill from *normalized*, or create a new one.

    Waterfall rule: only fill fields that are empty/missing on the existing lead
    (never overwrite a non-empty field).  Per-field provenance is stamped for
    every field that is written.  ``build_validation`` is re-run whenever a
    contact field changes so the gate stored in ``validation_json`` stays current.

    All identifiers are generic: ``source_key`` and ``license`` are opaque data
    values — no vendor or recipe strings belong in this function.
    """
    key = dedupe_key(normalized)
    enrichment = enrichment or {}
    addr = normalized.address or {}
    _country = addr.get("country") or country_override or ""

    existing = find_existing(session, key)

    # Fallback: if a richer-keyed lead (phone/domain) didn't match an existing
    # record, try name+city — handles the case where the existing record was
    # keyed by name+city only (no phone/domain at the time of first ingest).
    if existing is None and not key.startswith("name:"):
        _city = addr.get("city", "") or ""
        existing = find_existing(
            session, name_city_fallback_key(normalized.business_name, _city)
        )

    # ------------------------------------------------------------------ MERGE
    if existing is not None:
        changed_contact = False
        _CONTACT = {"phone", "public_email", "website_url"}

        # Simple string fields — waterfall: only fill when the target is empty.
        _simple = [
            ("business_name", normalized.business_name),
            ("phone", normalized.phone),
            ("public_email", normalized.public_email),
            ("website_url", normalized.website_url),
            ("address_line1", addr.get("line1", "")),
            ("city", addr.get("city", "")),
            ("region", addr.get("region", "")),
            ("postal_code", addr.get("postal_code", "")),
            ("country", _country),
        ]
        for fname, value in _simple:
            if value and not getattr(existing, fname, ""):
                setattr(existing, fname, value)
                stamp_provenance(existing, fname, source_key, license)
                if fname in _CONTACT:
                    changed_contact = True

        # Numeric geo: fill when the existing value is None.
        for fname, value in [("latitude", addr.get("lat")), ("longitude", addr.get("lon"))]:
            if value is not None and getattr(existing, fname) is None:
                setattr(existing, fname, value)
                stamp_provenance(existing, fname, source_key, license)

        # Category keys: fill when the existing list is empty.
        existing_cats: list = json.loads(existing.category_keys_json or "[]")
        if not existing_cats and normalized.category_keys:
            existing.category_keys_json = json.dumps(normalized.category_keys)
            stamp_provenance(existing, "category_keys", source_key, license)

        # Attributes: per-key waterfall — add only keys absent from existing.
        existing_attrs: dict = json.loads(existing.attributes_json or "{}")
        merged_attrs = dict(existing_attrs)
        for k, v in (normalized.attributes or {}).items():
            if k not in existing_attrs:
                merged_attrs[k] = v
                stamp_provenance(existing, f"attributes.{k}", source_key, license)
        if merged_attrs != existing_attrs:
            existing.attributes_json = json.dumps(merged_attrs)

        # Re-run contact validation when any contact field was filled.
        if changed_contact:
            ex_addr = {
                "line1": existing.address_line1 or "",
                "city": existing.city or "",
                "postal_code": existing.postal_code or "",
                "country": existing.country or "",
                "lat": existing.latitude,
                "lon": existing.longitude,
            }
            _val = build_validation({
                "email": existing.public_email,
                "phone": existing.phone,
                "country": existing.country or "",
                "address": {**ex_addr, "country": existing.country or ""},
                "intent": json.loads(existing.intent_json or "{}"),
                "name": existing.business_name,
                "category_keys": json.loads(existing.category_keys_json or "[]"),
                "city": existing.city or "",
                "opening_hours": "",
                "website_url": existing.website_url or "",
                "date_last_verified": existing.date_last_verified or _now(),
            })
            existing.validation_json = json.dumps(_val)
            existing.completeness_score = quality_score(_val)
            apply_tier_columns(existing, _val)

        session.add(existing)
        return existing

    # ----------------------------------------------------------------- CREATE
    _val = build_validation({
        "email": normalized.public_email,
        "phone": normalized.phone,
        "country": _country,
        "address": {
            "line1": addr.get("line1", ""),
            "city": addr.get("city", ""),
            "postal_code": addr.get("postal_code", ""),
            "country": _country,
            "lat": addr.get("lat"),
            "lon": addr.get("lon"),
        },
        "intent": enrichment,
        "name": normalized.business_name,
        "category_keys": normalized.category_keys,
        "city": addr.get("city", ""),
        "opening_hours": normalized.opening_hours or "",
        "website_url": normalized.website_url,
        "date_last_verified": _now(),
    })

    # Optional scoring — callers that supply a profile get subscores; others get 0.
    score_total, subscores_val, explanation = 0, {}, ""
    if scoring_profile is not None:
        ctx = {
            "category_keys": normalized.category_keys,
            "phone": normalized.phone,
            "public_email": normalized.public_email,
            "website_url": normalized.website_url,
            "attributes": {**normalized.attributes, **enrichment},
            "intent": enrichment,
            "date_last_verified": _now(),
            "source_confidence": 70,
            "opt_out_status": "clear",
            "suppression_status": "clear",
        }
        scored = score(ctx, scoring_profile)
        score_total = scored["total"]
        subscores_val = scored["subscores"]
        explanation = scored["explanation"]

    lead_obj = Lead(
        business_name=normalized.business_name,
        category_keys_json=json.dumps(normalized.category_keys),
        address_line1=addr.get("line1", ""),
        city=addr.get("city", ""),
        region=addr.get("region", ""),
        postal_code=addr.get("postal_code", ""),
        country=_country,
        latitude=addr.get("lat"),
        longitude=addr.get("lon"),
        phone=normalized.phone,
        public_email=normalized.public_email,
        website_url=normalized.website_url,
        attributes_json=json.dumps({**normalized.attributes, **enrichment}),
        intent_json=json.dumps(enrichment),
        score_total=score_total,
        subscores_json=json.dumps(subscores_val),
        score_explanation=explanation,
        scoring_profile_key=scoring_profile_key,
        source_key=source_key,
        source_name=source_name,
        source_url=source_url or normalized.source_url or "",
        source_license=license,
        attribution=attribution or source_key,
        date_last_verified=_now(),
        retention_expiry=expiry_for(_now()),
        dedupe_key=key,
        validation_json=json.dumps(_val),
        completeness_score=quality_score(_val),
    )
    apply_tier_columns(lead_obj, _val)
    session.add(lead_obj)
    session.flush()  # assign PK so stamp_provenance can reference it

    # Stamp provenance for every non-empty field contributed by this source.
    for fname in ("business_name", "phone", "public_email", "website_url",
                  "address_line1", "city", "region", "postal_code", "country"):
        if getattr(lead_obj, fname, ""):
            stamp_provenance(lead_obj, fname, source_key, license)
    if lead_obj.latitude is not None:
        stamp_provenance(lead_obj, "latitude", source_key, license)
    if lead_obj.longitude is not None:
        stamp_provenance(lead_obj, "longitude", source_key, license)
    for k in normalized.attributes or {}:
        stamp_provenance(lead_obj, f"attributes.{k}", source_key, license)

    session.add(lead_obj)
    return lead_obj


def ingest_normalized(
    session: Session,
    normalized_leads,
    *,
    source_key: str,
    source_license: str,
    source_name: str = "",
    source_url: str = "",
    attribution: str = "",
    scoring_profile_key: str = "",
    enrich_fn=enrich_website,
) -> dict:
    """Ingest pre-normalised leads via ``merge_or_create``.

    Each NormalizedLead either gap-fills an existing record (merge) or creates a
    new one.  Every lead passes through ``build_validation`` so the gate stored in
    ``validation_json`` is always current and enforced at serve time.

    ``source_key`` and ``source_license`` are opaque data values; no vendor or
    recipe strings belong here.
    """
    _profile = None
    if scoring_profile_key:
        try:
            _profile = profile_registry.get(scoring_profile_key)
        except KeyError:
            pass

    counts = {"normalized": 0, "stored": 0, "skipped_compliance": 0}

    for n in (normalized_leads or []):
        if n is None:
            continue
        counts["normalized"] += 1
        domain = host_of(n.website_url)
        if is_opted_out(session, domain=domain, phone=n.phone, email=n.public_email):
            counts["skipped_compliance"] += 1
            continue
        enrichment = enrich_fn(n)
        merge_or_create(
            session, n,
            source_key=source_key,
            license=source_license,
            scoring_profile=_profile,
            scoring_profile_key=scoring_profile_key,
            attribution=attribution,
            source_name=source_name,
            source_url=source_url,
            enrichment=enrichment,
        )
        counts["stored"] += 1

    session.commit()
    recompute_coverage(session)
    return counts
