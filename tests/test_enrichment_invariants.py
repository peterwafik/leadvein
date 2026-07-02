"""INV tests for externally-sourced and enriched leads.

Proves that the honesty spine (quality gate, masking, suppression, provenance,
ODbL attribution) applies identically to provider-sourced leads as it does to
OSM-origin leads.

Tests are GATE-ON by default (conftest registers the quality gate before each
test).  A test that turns the gate OFF must call clear_filters() and explain
why quality is orthogonal to what it exercises.
"""
from __future__ import annotations

import json

import pytest
from sqlmodel import Session

from app.adapters.base import FieldContribution, SourceMeta
from app.adapters.waterfall import run_enrichment
from app.core.db import (
    BuyerAccount, Lead, SuppressionEntry, SuppressionList, User, _now, init_db,
)
from app.core.leadcats import sync_lead_categories
from app.core.marketplace import search
from app.core.masking import mask_preview, unlock_view
from app.core.purchasing import LeadHeldBack, grant_credits, unlock_lead
from app.core.recipes import DEFAULT_FILTERS
from app.core.targeting.estimate import estimate
from app.targeting.runtime import register_targeting_runtime
from tests.quality_helpers import hot_validation_json


# ---------------------------------------------------------------------------
# Fake enrichment adapter (no live HTTP, no API key required)
# ---------------------------------------------------------------------------

class _FakeEnrichAdapter:
    """Always returns a single role-email FieldContribution.  No network I/O."""

    meta = SourceMeta(
        key="fake_enricher_inv",
        name="Fake Enricher INV",
        type="email_enrichment",
        url="https://example.com",
        license="Test License v1",
        terms_status="permitted",
        key_env="",          # key_env="" => always enabled (no env var needed)
        free_tier={"cap": 0, "window": "month"},   # cap=0 => unlimited
    )

    def enrich(self, view: dict) -> list[FieldContribution]:
        return [
            FieldContribution(
                field="public_email",
                value="info@acme-inv.example.com",
                license="Test License v1",
            )
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _buyer(session):
    """Create a BuyerAccount + User with 50 credits.  Returns (ba, user)."""
    ba = BuyerAccount(company_name="InvTestBuyer", credits=0,
                      compliance_ack_at=_now())
    session.add(ba)
    session.commit()
    session.refresh(ba)
    u = User(email=f"inv-buyer-{ba.id}@test.local", password_hash="x",
             role="buyer", buyer_account_id=ba.id)
    session.add(u)
    session.commit()
    session.refresh(u)
    grant_credits(session, ba.id, 50)
    return ba, u


def _ch_lead(session, *, validation_json, **overrides):
    """Seed a Companies House-sourced lead and sync its categories."""
    lead = Lead(
        business_name="Acme Widgets Ltd",
        category_keys_json=json.dumps(["retail"]),
        city="London",
        country="GB",
        phone="+44 20 1234 5678",
        public_email="info@acme.example.com",
        website_url="https://acme.example.com",
        score_total=80,
        date_last_verified=_now(),
        price_credits=2,
        source_key="companies_house",
        source_name="Companies House",
        source_license="Companies House data / Open Government Licence v3.0",
        attribution=(
            "Contains public sector information licensed under the "
            "Open Government Licence v3.0. Source: Companies House."
        ),
        validation_json=validation_json,
        **overrides,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    sync_lead_categories(session, lead)
    return lead


# ---------------------------------------------------------------------------
# INV-Q1 for external leads: quality gate is source-agnostic
# ---------------------------------------------------------------------------

def test_inv_q1_cold_external_lead_held_back():
    """A CH-sourced lead with no validated business contact is held back at all
    three serve points (search, composer estimate, unlock) — identical to a cold
    OSM lead.  The gate is source-agnostic.
    """
    # conftest already enables the gate; register targeting predicates for estimate
    register_targeting_runtime()

    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u = _buyer(s)

        # Cold validation: profile present but no validated business contact
        cold_val = json.dumps({
            "profile": {"present": True, "validated": True, "tier": "validated"},
            "email":   {"present": True, "validated": False, "tier": "present"},
            "phone":   {"present": True, "validated": False, "tier": "present"},
        })
        cold = _ch_lead(s, validation_json=cold_val)

        f = {**DEFAULT_FILTERS, "categories": ["retail"], "city": "London"}

        # 1. SEARCH — must be absent
        assert search(s, ba.id, f) == [], (
            "INV-Q1(ext): cold CH lead must be absent from marketplace search"
        )

        # 2. ESTIMATE (composer) — count 0, no samples
        comp = {
            "op": "AND",
            "nodes": [{"predicate": "geo.city", "params": {"value": "London"}}],
        }
        est = estimate(s, ba.id, comp)
        assert est["count"] == 0, (
            "INV-Q1(ext): cold CH lead must not be counted in composer estimate"
        )
        assert est["samples"] == [], (
            "INV-Q1(ext): cold CH lead must not appear in estimate samples"
        )

        # 3. UNLOCK — must be blocked
        with pytest.raises(LeadHeldBack):
            unlock_lead(s, u, cold.id)


def test_inv_q1_hot_external_lead_surfaces_normally():
    """A CH-sourced lead with a validated business contact clears all three
    gates — identical behaviour to a hot OSM lead.
    """
    register_targeting_runtime()

    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u = _buyer(s)

        hot = _ch_lead(s, validation_json=hot_validation_json())

        f = {**DEFAULT_FILTERS, "categories": ["retail"], "city": "London"}

        # 1. SEARCH — present
        results = search(s, ba.id, f)
        assert len(results) == 1, (
            "INV-Q1(ext): hot CH lead must surface in marketplace search"
        )

        # 2. ESTIMATE (composer) — counted
        comp = {
            "op": "AND",
            "nodes": [{"predicate": "geo.city", "params": {"value": "London"}}],
        }
        est = estimate(s, ba.id, comp)
        assert est["count"] == 1, (
            "INV-Q1(ext): hot CH lead must be counted in composer estimate"
        )
        assert len(est["samples"]) == 1, (
            "INV-Q1(ext): hot CH lead must appear in estimate samples"
        )

        # 3. UNLOCK — permitted
        purchase = unlock_lead(s, u, hot.id)
        assert purchase is not None, (
            "INV-Q1(ext): hot CH lead must be unlockable"
        )


# ---------------------------------------------------------------------------
# Spine parity (a): masking hides enriched contact on preview cards
# ---------------------------------------------------------------------------

def test_spine_masking_hides_enriched_contact():
    """mask_preview NEVER exposes public_email or phone for an enriched lead —
    the same masking rule that applies to OSM leads applies to provider-sourced
    and post-enrichment leads.
    """
    lead = Lead(
        business_name="Enriched Biz",
        category_keys_json=json.dumps(["retail"]),
        city="London",
        country="GB",
        phone="+44 20 9999 0001",
        public_email="info@enriched.example.com",
        website_url="https://enriched.example.com",
        score_total=80,
        price_credits=1,
        source_key="companies_house",
        source_name="Companies House",
    )
    preview = mask_preview(lead)
    blob = json.dumps(preview).lower()

    # Actual contact values must be absent from the preview
    assert "info@enriched.example.com" not in blob, (
        "Spine masking: enriched email must not appear in mask_preview"
    )
    assert "+44 20 9999 0001" not in blob, (
        "Spine masking: enriched phone must not appear in mask_preview"
    )
    assert "enriched.example.com" not in blob, (
        "Spine masking: enriched website must not appear in mask_preview"
    )

    # Presence flags are TRUE (buyer knows the lead has contact info)
    assert preview["has_email"] is True, (
        "Spine masking: has_email must be True when email is present"
    )
    assert preview["has_phone"] is True, (
        "Spine masking: has_phone must be True when phone is present"
    )
    assert preview["has_website"] is True, (
        "Spine masking: has_website must be True when website_url is present"
    )


# ---------------------------------------------------------------------------
# Spine parity (b): suppression blocks externally-sourced leads at serve time
# ---------------------------------------------------------------------------

def test_spine_suppression_blocks_external_lead():
    """Suppressing an external lead's domain blocks it at search and estimate —
    identical to suppression of an OSM lead.
    """
    register_targeting_runtime()

    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u = _buyer(s)

        # Hot validation — the lead WOULD surface without suppression
        lead = _ch_lead(s, validation_json=hot_validation_json())

        # Suppress the lead's domain for this buyer
        sup_list = SuppressionList(buyer_account_id=ba.id, name="ext-suppress")
        s.add(sup_list)
        s.commit()
        s.refresh(sup_list)
        s.add(SuppressionEntry(
            list_id=sup_list.id,
            kind="domain",
            value="acme.example.com",
        ))
        s.commit()

        f = {**DEFAULT_FILTERS, "categories": ["retail"], "city": "London"}

        # SEARCH — blocked by suppression
        results = search(s, ba.id, f)
        assert results == [], (
            "Spine suppression: suppressed external lead must be absent from marketplace search"
        )

        # ESTIMATE (composer) — blocked by suppression
        comp = {
            "op": "AND",
            "nodes": [{"predicate": "geo.city", "params": {"value": "London"}}],
        }
        est = estimate(s, ba.id, comp)
        assert est["count"] == 0, (
            "Spine suppression: suppressed external lead must not be counted in estimate"
        )
        assert est["samples"] == [], (
            "Spine suppression: suppressed external lead must not appear in estimate samples"
        )


# ---------------------------------------------------------------------------
# Spine parity (c): per-field provenance stamped by run_enrichment
# ---------------------------------------------------------------------------

def test_spine_provenance_stamped_by_enrichment():
    """After run_enrichment fills a field via a fake adapter, field_provenance_json
    carries {source, license, at} for that field.
    """
    engine = init_db("sqlite://")
    with Session(engine) as s:
        # Lead with no public_email — enrichment will fill it
        lead = Lead(
            business_name="Prov Test Biz",
            source_key="companies_house",
            public_email="",
            website_url="https://provtest.example.com",
            validation_json="{}",
        )
        s.add(lead)
        s.commit()
        s.refresh(lead)

        adapter = _FakeEnrichAdapter()
        run_enrichment(s, lead, [adapter])
        s.refresh(lead)

        # Field was filled
        assert lead.public_email == "info@acme-inv.example.com", (
            "Spine provenance: enrichment must fill public_email"
        )

        # Provenance blob carries {source, license, at} for the filled field
        prov = json.loads(lead.field_provenance_json or "{}")
        assert "public_email" in prov, (
            "Spine provenance: field_provenance_json must have an entry for public_email"
        )
        entry = prov["public_email"]
        assert entry.get("source") == "Fake Enricher INV", (
            "Spine provenance: source must match the adapter's name"
        )
        assert entry.get("license") == "Test License v1", (
            "Spine provenance: license must match the FieldContribution license"
        )
        assert "at" in entry, (
            "Spine provenance: provenance entry must have an 'at' timestamp"
        )


# ---------------------------------------------------------------------------
# Spine parity (d): OSM-origin attribution is preserved even after enrichment
# ---------------------------------------------------------------------------

def test_spine_osm_attribution_survives_enrichment():
    """An OSM-sourced lead retains ODbL attribution after enrichment fills an
    additional field.  Enrichment stamps per-field provenance for the filled
    field but must NOT overwrite source_license or attribution.
    """
    engine = init_db("sqlite://")
    with Session(engine) as s:
        # OSM-origin lead missing a public_email
        lead = Lead(
            business_name="OSM Diner",
            source_key="osm",
            source_name="OpenStreetMap (Overpass)",
            source_license="ODbL 1.0",
            attribution="© OpenStreetMap contributors, ODbL 1.0",
            public_email="",
            website_url="https://osm-diner.example.com",
            validation_json="{}",
        )
        s.add(lead)
        s.commit()
        s.refresh(lead)

        adapter = _FakeEnrichAdapter()
        run_enrichment(s, lead, [adapter])
        s.refresh(lead)

        # Enrichment filled the missing email
        assert lead.public_email == "info@acme-inv.example.com", (
            "Spine ODbL: enrichment must fill the missing public_email"
        )

        # Source-level ODbL attribution is UNTOUCHED
        assert "ODbL" in lead.source_license, (
            "Spine ODbL: source_license must still carry 'ODbL' after enrichment"
        )
        assert "OpenStreetMap" in lead.attribution, (
            "Spine ODbL: attribution must still carry 'OpenStreetMap' after enrichment"
        )

        # unlock_view exposes the source-level attribution (not masked)
        view = unlock_view(lead)
        assert "ODbL" in view["source_license"], (
            "Spine ODbL: unlock_view must expose ODbL source_license"
        )
        assert "OpenStreetMap" in view["attribution"], (
            "Spine ODbL: unlock_view must expose OpenStreetMap attribution"
        )

        # Per-field provenance carries the enrichment license for the enriched field
        prov = json.loads(lead.field_provenance_json or "{}")
        assert prov.get("public_email", {}).get("license") == "Test License v1", (
            "Spine ODbL: enriched-field provenance must carry the enrichment license, "
            "not ODbL (ODbL belongs to the source-level attribution)"
        )
