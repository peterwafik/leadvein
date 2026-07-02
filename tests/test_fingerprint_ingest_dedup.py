"""Tests for Task 3: fingerprint-sourced leads through gate + dedup + provenance.

INV-Q1  — a lead with no validated contact is held back by the quality gate;
           one with a validated phone surfaces as hot.
INV-14  — the same business ingested from two sources (OSM then a tech-detection
           source) produces ONE Lead row; field_provenance_json records which
           source contributed each field; merged attributes carry the tech key.
masking — email and phone are hidden on a masked marketplace card while the
           has_phone / has_email presence flags remain True.
"""
from __future__ import annotations

import json

import pytest
from sqlmodel import Session, select

from app.adapters.base import NormalizedLead
from app.core.db import init_db, Lead
from app.ingestion.pipeline import merge_or_create
from app.core.masking import mask_preview
from app.core.serve_filters import register_serve_filter, passes_serve_filters
from app.core.serve_filters import clear as _clear_filters
from app.quality.serve_gate import quality_serve_filter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OSM_KEY = "osm"
_OSM_LIC = "ODbL"
_FP_KEY = "tech_detection_src"
_FP_LIC = "tech_detection_tos"

VALID_PHONE = "+44 7911 123456"  # valid UK mobile — phonenumbers.is_valid_number == True


def _osm_normalized(domain: str, *, name: str = "Test Pizza") -> NormalizedLead:
    """OSM-style lead: address + category, a website domain, no phone."""
    return NormalizedLead(
        business_name=name,
        category_keys=["restaurant"],
        address={
            "line1": "123 High St",
            "city": "London",
            "postal_code": "SW1A 1AA",
            "country": "GB",
            "lat": 51.5,
            "lon": -0.1,
        },
        website_url=f"https://{domain}",
        phone="",
        public_email="",
        source_key=_OSM_KEY,
        source_license=_OSM_LIC,
    )


def _fp_normalized(domain: str, *, phone: str = "", email: str = "",
                   name: str = "Test Pizza") -> NormalizedLead:
    """Tech-detection-style lead: website + contact + recipe attributes."""
    return NormalizedLead(
        business_name=name,
        category_keys=[],
        address={},
        website_url=f"https://{domain}",
        phone=phone,
        public_email=email,
        attributes={
            "recipe_key": "food_delivery_platform_v1",
            "matched": True,
            "match_strength": 0.9,
        },
        source_key=_FP_KEY,
        source_license=_FP_LIC,
    )


def _mk_engine():
    return init_db("sqlite://")


# ---------------------------------------------------------------------------
# INV-Q1: quality gate holds back leads without validated contact
# ---------------------------------------------------------------------------

def test_inv_q1_fingerprint_lead_no_contact_is_held():
    """A tech-detection lead with no validated contact must NOT pass the gate."""
    _clear_filters()
    register_serve_filter(quality_serve_filter)
    try:
        engine = _mk_engine()
        with Session(engine) as session:
            cold = NormalizedLead(
                business_name="Cold Cafe",
                category_keys=["cafe"],
                address={"city": "London"},
                website_url="https://coldcafe-test.co.uk",
                phone="",
                public_email="",
                source_key=_FP_KEY,
                source_license=_FP_LIC,
            )
            lead = merge_or_create(
                session, cold, source_key=_FP_KEY, license=_FP_LIC
            )
            session.commit()
            session.refresh(lead)

            # Gate must reject — no validated contact
            assert not passes_serve_filters(session, buyer_account_id=1, lead=lead), (
                "Cold lead (no validated contact) must be held back by the quality gate"
            )
    finally:
        _clear_filters()


def test_inv_q1_fingerprint_lead_with_valid_phone_surfaces():
    """A tech-detection lead with a validated phone must pass the quality gate."""
    _clear_filters()
    register_serve_filter(quality_serve_filter)
    try:
        engine = _mk_engine()
        with Session(engine) as session:
            hot = NormalizedLead(
                business_name="Hot Pizza",
                category_keys=["restaurant"],
                address={"city": "London"},
                website_url="https://hotpizza-test.co.uk",
                phone=VALID_PHONE,
                public_email="",
                source_key=_FP_KEY,
                source_license=_FP_LIC,
            )
            lead = merge_or_create(
                session, hot, source_key=_FP_KEY, license=_FP_LIC
            )
            session.commit()
            session.refresh(lead)

            # Gate must pass — valid UK mobile
            assert passes_serve_filters(session, buyer_account_id=1, lead=lead), (
                "Hot lead (validated phone) must surface through the quality gate"
            )
    finally:
        _clear_filters()


# ---------------------------------------------------------------------------
# INV-14: cross-source dedup — ONE lead row with per-field provenance
# ---------------------------------------------------------------------------

def test_inv_14_same_business_two_sources_produces_one_lead():
    """OSM lead + tech-detection lead for the same domain → ONE Lead row."""
    engine = _mk_engine()
    with Session(engine) as session:
        domain = "merge-pizza-test.co.uk"

        # Step 1: ingest via OSM (address + category, no contact)
        osm_n = _osm_normalized(domain)
        osm_lead = merge_or_create(
            session, osm_n, source_key=_OSM_KEY, license=_OSM_LIC
        )
        session.commit()
        session.refresh(osm_lead)
        osm_id = osm_lead.id

        # Sanity: one row, no phone yet
        all_leads = session.exec(select(Lead)).all()
        assert len(all_leads) == 1
        assert all_leads[0].phone == ""

        # Step 2: tech-detection source finds the same domain, adds phone + attrs
        fp_n = _fp_normalized(domain, phone=VALID_PHONE)
        merged = merge_or_create(
            session, fp_n, source_key=_FP_KEY, license=_FP_LIC
        )
        session.commit()
        session.refresh(merged)

        # Must still be ONE lead, same row
        all_leads = session.exec(select(Lead)).all()
        assert len(all_leads) == 1, (
            f"Expected 1 lead after cross-source merge, got {len(all_leads)}"
        )
        assert merged.id == osm_id, "merge_or_create must return the existing lead, not a new one"

        # Phone must now be filled from the tech-detection source
        assert merged.phone == VALID_PHONE

        # Provenance: address fields from OSM, phone from tech-detection
        prov = json.loads(merged.field_provenance_json)

        assert prov.get("address_line1", {}).get("source") == _OSM_KEY, (
            f"address_line1 provenance should be {_OSM_KEY!r}, got {prov.get('address_line1')}"
        )
        assert prov.get("city", {}).get("source") == _OSM_KEY, (
            f"city provenance should be {_OSM_KEY!r}, got {prov.get('city')}"
        )
        assert prov.get("phone", {}).get("source") == _FP_KEY, (
            f"phone provenance should be {_FP_KEY!r}, got {prov.get('phone')}"
        )

        # Tech attributes must be merged — including recipe_key
        attrs = json.loads(merged.attributes_json)
        assert attrs.get("recipe_key") == "food_delivery_platform_v1", (
            f"attributes.recipe_key missing or wrong: {attrs}"
        )
        assert attrs.get("matched") is True

        # Attribute provenance must point to the tech-detection source
        assert prov.get("attributes.recipe_key", {}).get("source") == _FP_KEY


def test_inv_14_osm_fields_are_not_overwritten_by_tech_source():
    """Waterfall rule: OSM address must survive when tech-detection re-ingests the same domain."""
    engine = _mk_engine()
    with Session(engine) as session:
        domain = "waterfall-test.co.uk"
        osm_n = _osm_normalized(domain, name="Waterfall Restaurant")
        merge_or_create(session, osm_n, source_key=_OSM_KEY, license=_OSM_LIC)
        session.commit()

        # Tech-detection tries to supply a different city — must NOT overwrite
        fp_n = NormalizedLead(
            business_name="Waterfall Restaurant",
            category_keys=[],
            address={"city": "Manchester"},  # different city — must be ignored
            website_url=f"https://{domain}",
            phone=VALID_PHONE,
            source_key=_FP_KEY,
            source_license=_FP_LIC,
        )
        merged = merge_or_create(session, fp_n, source_key=_FP_KEY, license=_FP_LIC)
        session.commit()
        session.refresh(merged)

        # OSM city must be preserved
        assert merged.city == "London", (
            f"Waterfall rule violated: city was overwritten to {merged.city!r}"
        )


# ---------------------------------------------------------------------------
# masking: contact hidden in marketplace card; presence flags remain True
# ---------------------------------------------------------------------------

def test_masking_hides_contact_on_fingerprint_lead():
    """mask_preview must hide phone and email while keeping has_phone/has_email True."""
    engine = _mk_engine()
    with Session(engine) as session:
        n = NormalizedLead(
            business_name="Mask Pizza",
            category_keys=["restaurant"],
            address={"city": "London"},
            website_url="https://maskpizza-test.co.uk",
            phone=VALID_PHONE,
            public_email="orders@maskpizza-test.co.uk",
            source_key=_FP_KEY,
            source_license=_FP_LIC,
        )
        lead = merge_or_create(session, n, source_key=_FP_KEY, license=_FP_LIC)
        session.commit()
        session.refresh(lead)

        preview = mask_preview(lead)
        blob = json.dumps(preview)

        # Contact values must be absent from the preview blob
        assert VALID_PHONE not in blob, "mask_preview must not expose phone number"
        assert "orders@maskpizza-test.co.uk" not in blob, "mask_preview must not expose email"
        assert "maskpizza-test.co.uk" not in blob or preview.get("website_url") is None, (
            "mask_preview must not expose the business domain"
        )

        # Presence flags must signal that contact details exist
        assert preview["has_phone"] is True, "has_phone must be True when phone is set"
        assert preview["has_email"] is True, "has_email must be True when email is set"
        assert preview["has_website"] is True, "has_website must be True when website is set"


def test_masking_presence_flags_false_when_no_contact():
    """has_phone and has_email must be False when the lead carries no contact."""
    engine = _mk_engine()
    with Session(engine) as session:
        n = NormalizedLead(
            business_name="Silent Pizza",
            category_keys=["restaurant"],
            address={"city": "London"},
            website_url="https://silentpizza-test.co.uk",
            phone="",
            public_email="",
            source_key=_FP_KEY,
            source_license=_FP_LIC,
        )
        lead = merge_or_create(session, n, source_key=_FP_KEY, license=_FP_LIC)
        session.commit()
        session.refresh(lead)

        preview = mask_preview(lead)
        assert preview["has_phone"] is False
        assert preview["has_email"] is False
