"""Tier ordinals: indexed int mirrors of validation_json tiers.

Single-writer rule: apply_tier_columns is the only code that writes tier_*
columns, and it is invoked at every site that writes validation_json — so the
columns can never drift from the JSON. INV-Q1 note: these columns are a SQL
PRE-NARROWING layer; the Python gate stays authoritative (tested in Task 10).
"""
from __future__ import annotations

import json

from sqlmodel import Session, select

import app.leadvault as lv
from app.adapters.base import NormalizedLead
from app.core.db import Lead
from app.ingestion.pipeline import ingest_normalized
from app.quality.ordinals import apply_tier_columns, ordinal
from app.quality.tiers import TIER_ORDER


def test_ordinal_maps_tier_order():
    assert ordinal("absent") == 0
    assert ordinal("present") == 1
    assert ordinal("validated") == 2
    assert ordinal("verified_live") == 3
    assert ordinal("bogus") == 0          # fail closed


def test_apply_tier_columns_mirrors_json():
    lead = Lead(business_name="T")
    val = {"phone": {"tier": "validated"}, "email": {"tier": "present"},
           "address": {"tier": "absent"}, "website": {"tier": "present"},
           "profile": {"tier": "validated"}, "freshness": {"tier": "validated"}}
    apply_tier_columns(lead, val)
    assert lead.tier_phone == 2 and lead.tier_email == 1
    assert lead.tier_address == 0 and lead.tier_website == 1
    assert lead.tier_profile == 2
    assert lead.tier_contact == 2          # max(phone, email)


def test_ingest_normalized_stamps_columns():
    n = NormalizedLead(
        business_name="Ordinal Bakery", category_keys=["bakery"],
        address={"city": "Ordinalville", "country": "GB"},
        phone="+441865000001", raw_ref="node/991")
    with Session(lv.engine) as s:
        ingest_normalized(s, [n], source_key="osm_geofabrik",
                          source_license="ODbL", enrich_fn=lambda _n: {})
        lead = s.exec(select(Lead).where(
            Lead.business_name == "Ordinal Bakery")).first()
        val = json.loads(lead.validation_json)
        assert lead.tier_phone == TIER_ORDER.index(val["phone"]["tier"])
        assert lead.tier_contact >= lead.tier_phone or lead.tier_contact >= lead.tier_email


def test_merge_path_restamps_columns():
    # Both leads share ONE dedup identity: name:merge-ord|ordinalville
    # (neither has phone nor website).  fill adds public_email so the merge
    # branch fires changed_contact, re-runs validation, and restamps ordinals.
    base = NormalizedLead(business_name="Merge Ord", category_keys=["cafe"],
                          address={"city": "Ordinalville", "country": "GB"},
                          raw_ref="node/992")
    fill = NormalizedLead(business_name="Merge Ord", category_keys=["cafe"],
                          address={"city": "Ordinalville", "country": "GB"},
                          public_email="merge@ord.example",
                          raw_ref="node/993")
    with Session(lv.engine) as s:
        ingest_normalized(s, [base], source_key="osm_geofabrik",
                          source_license="ODbL", enrich_fn=lambda _n: {})
        lead = s.exec(select(Lead).where(Lead.business_name == "Merge Ord")).first()
        before_email = lead.tier_email
        ingest_normalized(s, [fill], source_key="osm_geofabrik",
                          source_license="ODbL", enrich_fn=lambda _n: {})
        s.refresh(lead)
        assert before_email == 0
        assert lead.tier_email >= 1          # present or validated after email filled
        assert lead.tier_contact >= 1        # tier_contact = max(tier_phone, tier_email)
