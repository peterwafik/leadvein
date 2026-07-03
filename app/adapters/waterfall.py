"""Waterfall enrichment runner.

For each adapter in order:
  1. Skip if not enabled (missing API key).
  2. Skip if ToS-restricted (terms_status == "restricted").
  3. Skip if free-tier cap would be exceeded (cap=0 means unlimited/free-unmetered).
  4. Call adapter.enrich(lead_view(lead)).
  5. Record one budget use per adapter INVOCATION (not per fill).
     cap=0 means unlimited/unmetered (e.g. Companies House) — no metering.
  6. For each FieldContribution: apply only if the field is missing or unverified
     (empty, or its validation tier is below "validated").
     When applied: set the field, re-validate it into validation_json,
     stamp_provenance.
  7. Commit the lead.

Returns {source_key: fill_count} for each adapter that was not skipped.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlmodel import Session

from app.adapters import registry
from app.adapters.budget import would_exceed, record_use, stamp_provenance
from app.core.targeting.view import lead_view
from app.quality.tiers import TIER_ORDER, achieved_tier
from app.quality.ordinals import apply_tier_columns

if TYPE_CHECKING:
    from app.core.db import Lead


# ---------------------------------------------------------------------------
# Field-to-validation-key mapping
# ---------------------------------------------------------------------------

# Maps a Lead attribute name to the key used inside validation_json
_FIELD_TO_VAL_KEY: dict[str, str] = {
    "phone": "phone",
    "public_email": "email",
    "website_url": "website",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _field_tier(lead, field: str) -> str:
    """Return the current quality tier for *field* from lead.validation_json."""
    try:
        val: dict = json.loads(lead.validation_json or "{}")
    except (ValueError, TypeError):
        val = {}
    val_key = _FIELD_TO_VAL_KEY.get(field, field)
    blob = val.get(val_key) or {}
    return blob.get("tier", "absent")


def _is_below_validated(tier: str) -> bool:
    """Return True when *tier* is below 'validated' (i.e. absent or present)."""
    if tier not in TIER_ORDER:
        return True  # unknown → treat as unverified (safe default)
    return TIER_ORDER.index(tier) < TIER_ORDER.index("validated")


def _revalidate_field(lead, field: str, value: object) -> None:
    """Re-run field-specific validation and update lead.validation_json in place.

    Uses offline validators only (no live MX / network calls from the runner).
    """
    from app.quality.validators.phone import validate_phone
    from app.quality.validators.email import validate_email

    try:
        val: dict = json.loads(lead.validation_json or "{}")
    except (ValueError, TypeError):
        val = {}

    if field == "phone":
        country = (getattr(lead, "country", "") or "").strip().upper()
        region = country if len(country) == 2 else "GB"
        blob = validate_phone(str(value or ""), region=region)
        blob["tier"] = achieved_tier(blob)
        val["phone"] = blob

    elif field == "public_email":
        # No live MX lookup during enrichment — offline syntax + disposable check only.
        blob = validate_email(str(value or ""), mx_lookup=lambda _d: False)
        blob["tier"] = achieved_tier(blob)
        val["email"] = blob

    # For other fields there is no dedicated field validator yet; leave validation_json alone.

    lead.validation_json = json.dumps(val)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_enrichment(
    session: Session,
    lead,
    adapters: list,
    *,
    http=None,  # reserved for future use; adapters manage their own http clients
) -> dict[str, int]:
    """Apply *adapters* to *lead*, filling gaps only.

    Returns ``{source_key: fill_count}`` for each adapter that was not skipped.
    """
    counts: dict[str, int] = {}

    for adapter in adapters:
        meta = adapter.meta
        source_key = meta.key

        # 1. Skip if disabled (API key absent)
        if not registry.enabled(adapter):
            continue

        # 2. Skip if ToS-restricted
        if meta.terms_status == "restricted":
            continue

        # 3. Check free-tier budget.
        #    cap=0 means unlimited/free-unmetered — do NOT skip.
        cap: int = meta.free_tier.get("cap", 0)
        if cap != 0 and would_exceed(session, source_key, cap, 1):
            continue

        # 4. Enrich
        view = lead_view(lead)
        contribs = adapter.enrich(view)

        # 5. Record one budget use per adapter INVOCATION that hit the provider.
        #    DEFAULT 1 — conservative: if an adapter does not set api_calls_last,
        #    assume it made a call so we never undercount and overrun the free tier.
        #    cap=0 means unlimited/unmetered (e.g. Companies House) — skip metering.
        #    NOTE: this read-modify-write is non-atomic; fine for single-worker.
        #    A multi-worker deployment would need an atomic SQL UPDATE (used=used+n).
        calls = getattr(adapter, "api_calls_last", 1)
        if calls > 0 and cap > 0:
            record_use(session, source_key, cap, calls)

        fill_count = 0
        for contrib in contribs:
            field = contrib.field
            current_value = getattr(lead, field, None)

            # 6. Apply only if missing or unverified
            is_missing = not current_value
            current_tier = _field_tier(lead, field)
            is_unverified = _is_below_validated(current_tier)

            if not (is_missing or is_unverified):
                continue  # field already has a validated/verified value

            # Apply the contribution
            setattr(lead, field, contrib.value)

            # Re-validate this field (offline) and restamp tier ordinals
            _revalidate_field(lead, field, contrib.value)
            apply_tier_columns(lead, json.loads(lead.validation_json or "{}"))

            # Stamp provenance (budget already counted above — once per invocation)
            stamp_provenance(lead, field, meta.name, contrib.license)

            fill_count += 1

        counts[source_key] = fill_count

        # Commit lead changes for this adapter (record_use may have already
        # committed, but an explicit add+commit ensures the lead is persisted
        # even when fill_count == 0).
        session.add(lead)
        session.commit()

    return counts
