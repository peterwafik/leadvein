"""Admin bulk unlock / export — economy-bypassing, compliance-intact.

INVARIANT: this module imports NOTHING from app.core.purchasing.
No PurchasedLead rows, no CreditTransaction rows, no times_sold changes.
Compliance spine (expiry, opt-out, serve filters) still applied.
Suppression: the owner path applies GLOBAL suppression (build_suppression_index
with buyer_account_id=None) — matching what the admin's on-screen estimate
applies — but never buyer-scoped suppression (there is no buyer in an owner view).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlmodel import Session

from app.core.compliance import audit, build_optout_index, lead_opted_out
from app.core.db import Lead
from app.core.export_leads import EXPORT_COLUMNS
from app.core.marketplace import build_suppression_index
from app.core.masking import unlock_view
from app.core.retention import is_expired
from app.core.serve_filters import passes_serve_filters
from app.core.targeting.composition import matching_by_composition
from app.engine.export import _stringify, rows_to_xlsx
from app.quality.tiers import TIER_ORDER
from app.quality.visibility import with_quality
from app.web.csrf import csrf_protect, csrf_protect_json
from app.web.deps import get_session, current_user

router = APIRouter(prefix="/admin/bulk")


def _valid_composition(node) -> bool:
    """Minimal structural check — rejects degenerate or predicate-less compositions.

    A valid composition is either:
    - A compound node: dict with op in ("AND","OR") and nodes as a list of valid nodes
    - A leaf node: dict with a non-empty "predicate" string
    Returns False for {} or any node missing "predicate".
    """
    if not isinstance(node, dict):
        return False
    if "op" in node:
        if node["op"] not in ("AND", "OR"):
            return False
        nodes = node.get("nodes", [])
        if not isinstance(nodes, list):
            return False
        return all(_valid_composition(child) for child in nodes)
    # Leaf node: must have a non-empty predicate string
    return isinstance(node.get("predicate"), str) and bool(node["predicate"])


# Hard cap on a single export — both id-list and composition modes.  Guards against
# a whole-inventory dump; narrow the targeting to fit.  (Module-level so tests can
# monkeypatch it to a small value instead of seeding tens of thousands of rows.)
MAX_EXPORT_ROWS = 10_000

# Export columns: standard set + geo + tier labels + provenance
BULK_EXPORT_COLUMNS = EXPORT_COLUMNS + [
    "latitude",
    "longitude",
    "tier_phone_label",
    "tier_email_label",
    "tier_address_label",
    "tier_website_label",
    "provenance_summary",
]


def _admin(request: Request, session: Session):
    u = current_user(request, session)
    return u if (u and u.role == "admin") else None


def _is_serveable(session: Session, lead, sup=None) -> bool:
    """Compliance-spine check for owner (admin) view.

    Applies GLOBAL suppression (when a SuppressionIndex is passed) but never
    buyer-scoped suppression — there is no buyer in an owner view.
    """
    if is_expired(lead):
        return False
    if lead_opted_out(session, lead):
        return False
    if sup is not None and sup.is_suppressed(lead):
        return False
    if not passes_serve_filters(session, None, lead, None):
        return False
    return True


def _make_export_row(lead) -> dict:
    """Full unlocked row with tier labels and provenance for export."""
    val = json.loads(lead.validation_json or "{}")

    def tier_label(field: str) -> str:
        fb = val.get(field) or {}
        t = fb.get("tier", "absent")
        return t if t in TIER_ORDER else "absent"

    prov_parts = []
    for field in ("phone", "email", "address", "website"):
        fb = val.get(field) or {}
        source = fb.get("source", "")
        if source:
            prov_parts.append(f"{field}:{source}")

    row = with_quality(unlock_view(lead), lead)
    row["tier_phone_label"] = tier_label("phone")
    row["tier_email_label"] = tier_label("email")
    row["tier_address_label"] = tier_label("address")
    row["tier_website_label"] = tier_label("website")
    row["provenance_summary"] = ", ".join(prov_parts)
    return row


@router.post("/reveal", dependencies=[Depends(csrf_protect_json)])
async def bulk_reveal(request: Request, session: Session = Depends(get_session)):
    """Return full unlock_view rows for serveable leads — no economy side effects."""
    u = _admin(request, session)
    if not u:
        return Response(status_code=403)

    try:
        body = await request.json()
    except Exception:
        return Response(status_code=400)

    lead_ids = body.get("lead_ids", [])
    if not isinstance(lead_ids, list) or len(lead_ids) > 500:
        return Response(status_code=400)

    sup = build_suppression_index(session, None)   # global suppression only (owner view)
    results = []
    for lid in lead_ids:
        lead = session.get(Lead, lid)
        if lead is None:
            continue
        if not _is_serveable(session, lead, sup):
            continue
        results.append(with_quality(unlock_view(lead), lead))

    audit(session, u.id, "admin.bulk_unlock", "Lead", "*", {"count": len(results)})
    return JSONResponse({"leads": results})


@router.post("/export", dependencies=[Depends(csrf_protect)])
async def bulk_export(request: Request, session: Session = Depends(get_session)):
    """Stream CSV or XLSX export of serveable leads.  Economy entirely bypassed."""
    u = _admin(request, session)
    if not u:
        return Response(status_code=403)

    form = await request.form()
    fmt = (form.get("format") or "csv").lower()
    lead_ids_raw = str(form.get("lead_ids") or "").strip()
    composition_raw = str(form.get("composition") or "").strip()

    serveable_leads: list = []
    comp_hash: str | None = None
    sup = build_suppression_index(session, None)   # global suppression only (owner view)

    if lead_ids_raw:
        # Id-list mode — per-lead compliance check (typically ≤500)
        try:
            lead_ids = [int(x.strip()) for x in lead_ids_raw.split(",") if x.strip()]
        except ValueError:
            return Response(status_code=400)
        for lid in lead_ids:
            lead = session.get(Lead, lid)
            if lead is None:
                continue
            if not _is_serveable(session, lead, sup):
                continue
            serveable_leads.append(lead)

    elif composition_raw:
        # Composition mode — batch compliance check (could be 100k rows)
        try:
            composition = json.loads(composition_raw)
        except (json.JSONDecodeError, TypeError):
            return Response(status_code=400)
        if not _valid_composition(composition):
            return Response(
                content="Invalid targeting composition.",
                status_code=400,
                media_type="text/plain",
            )
        comp_hash = hashlib.sha256(
            json.dumps(composition, sort_keys=True).encode()
        ).hexdigest()[:16]
        leads = matching_by_composition(session, composition)
        optout = build_optout_index(session)   # one query, then in-memory
        for lead in leads:
            if is_expired(lead):
                continue
            if optout.matches(lead):
                continue
            if sup.is_suppressed(lead):   # global suppression (matches on-screen estimate)
                continue
            if not passes_serve_filters(session, None, lead, None):
                continue
            serveable_leads.append(lead)

    else:
        return Response(status_code=400)

    # Hard cap — refuse a whole-inventory dump; caller must narrow the targeting.
    if len(serveable_leads) > MAX_EXPORT_ROWS:
        return Response(
            content=(f"Export capped at {MAX_EXPORT_ROWS:,} rows — "
                     "narrow the targeting first."),
            status_code=400,
            media_type="text/plain",
        )

    rows = [_make_export_row(lead) for lead in serveable_leads]

    # Attribution — one leading metadata row (ODbL / source info)
    attributions = sorted({str(r.get("attribution") or "")
                           for r in rows if r.get("attribution")})
    attribution_str = ", ".join(attributions) if attributions else "LeadVault export"

    meta: dict = {"count": len(rows)}
    if comp_hash:
        meta["composition_hash"] = comp_hash
    audit(session, u.id, "admin.bulk_export", "Lead", "*", meta)

    if fmt == "xlsx":
        # Leading attribution row in the data (formula-injection guard via _stringify)
        attr_row: dict = {c: "" for c in BULK_EXPORT_COLUMNS}
        attr_row["business_name"] = attribution_str
        data = rows_to_xlsx("LeadVault Export", BULK_EXPORT_COLUMNS,
                            [attr_row] + rows)
        return Response(
            content=data,
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition":
                    'attachment; filename="leadvault-export.xlsx"'
            },
        )
    else:
        # CSV: attribution as the very first row (before the column header)
        buf = io.StringIO()
        writer = csv.writer(buf)
        # Attribution is data-derived — run it through the same formula-injection
        # guard as the data cells below (Excel/Sheets treat a leading =,+,-,@ as a formula).
        writer.writerow([_stringify(attribution_str)])   # leading metadata row
        writer.writerow(BULK_EXPORT_COLUMNS)     # column header
        for row in rows:
            # _stringify applies the same formula-injection guard as rows_to_csv
            writer.writerow([_stringify(row.get(c, "")) for c in BULK_EXPORT_COLUMNS])
        data = buf.getvalue().encode("utf-8")
        return Response(
            content=data,
            media_type="text/csv",
            headers={
                "Content-Disposition":
                    'attachment; filename="leadvault-export.csv"'
            },
        )
