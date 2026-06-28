from __future__ import annotations

import json

from sqlmodel import Session, select

from app.core.db import Lead, PurchasedLead


def mask_preview(lead: Lead) -> dict:
    return {
        "lead_id": lead.id,
        "category_keys": json.loads(lead.category_keys_json or "[]"),
        "city": lead.city, "region": lead.region, "country": lead.country,
        "score_total": lead.score_total,
        "subscores": json.loads(lead.subscores_json or "{}"),
        "reason": lead.score_explanation,
        "has_phone": bool(lead.phone), "has_email": bool(lead.public_email),
        "has_website": bool(lead.website_url),
        "price_credits": lead.price_credits,
        "exclusivity_status": lead.exclusivity_status,
        "source_type": lead.source_name,
        "freshness": lead.date_last_verified,
    }


def unlock_view(lead: Lead) -> dict:
    return {
        "lead_id": lead.id, "business_name": lead.business_name,
        "category_keys": json.loads(lead.category_keys_json or "[]"),
        "address_line1": lead.address_line1, "city": lead.city, "region": lead.region,
        "postal_code": lead.postal_code, "country": lead.country,
        "latitude": lead.latitude, "longitude": lead.longitude,
        "phone": lead.phone, "public_email": lead.public_email,
        "website_url": lead.website_url,
        "attributes": json.loads(lead.attributes_json or "{}"),
        "intent": json.loads(lead.intent_json or "{}"),
        "score_total": lead.score_total,
        "subscores": json.loads(lead.subscores_json or "{}"),
        "score_explanation": lead.score_explanation,
        "source_name": lead.source_name, "source_url": lead.source_url,
        "source_license": lead.source_license, "lawful_basis": lead.lawful_basis,
        "date_last_verified": lead.date_last_verified,
    }


def is_owned(session: Session, buyer_account_id: int, lead_id: int) -> bool:
    return session.exec(select(PurchasedLead).where(
        PurchasedLead.buyer_account_id == buyer_account_id,
        PurchasedLead.lead_id == lead_id)).first() is not None


def assert_owned(session: Session, buyer_account_id: int, lead_id: int) -> None:
    if not is_owned(session, buyer_account_id, lead_id):
        raise PermissionError(f"buyer {buyer_account_id} does not own lead {lead_id}")
