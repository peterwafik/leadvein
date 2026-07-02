"""Tests for the waterfall enrichment runner (Task 3).

TDD: tests are written to fail first, then implementation is provided.

Covers:
(a) An adapter already over its free cap is skipped (would_exceed).
(b) An adapter returning a role-email FieldContribution fills public_email on
    a lead missing it, stamps provenance, records use.
(c) A lead that ALREADY has a verified phone is NOT overwritten by a fake
    lower-tier phone contribution.
"""
from __future__ import annotations

import json

import pytest
from sqlmodel import Session

from app.core.db import init_db, Lead
from app.adapters.base import SourceMeta, FieldContribution
from app.adapters.budget import record_use


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def session():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        yield s


def _make_lead(session, *, phone="", public_email="", validation_json="{}"):
    lead = Lead(
        business_name="Test Biz",
        source_key="test",
        phone=phone,
        public_email=public_email,
        validation_json=validation_json,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


# ---------------------------------------------------------------------------
# Fake adapters
# ---------------------------------------------------------------------------

class FakeEmailAdapter:
    """Returns a role-email FieldContribution for any lead."""
    meta = SourceMeta(
        key="fake_email_src",
        name="Fake Email Source",
        type="enrichment",
        url="https://example.com",
        license="CC0",
        terms_status="permitted",
        key_env="",          # no key required; always enabled
        free_tier={"cap": 10, "window": "month"},
    )

    def enrich(self, view: dict) -> list[FieldContribution]:
        return [
            FieldContribution(
                field="public_email",
                value="info@testbiz.com",
                license="CC0",
                confidence=0.9,
            )
        ]


class FakePhoneAdapter:
    """Returns a phone FieldContribution — used to test no-overwrite."""
    meta = SourceMeta(
        key="fake_phone_src",
        name="Fake Phone Source",
        type="enrichment",
        url="https://example.com",
        license="CC0",
        terms_status="permitted",
        key_env="",
        free_tier={"cap": 10, "window": "month"},
    )

    def enrich(self, view: dict) -> list[FieldContribution]:
        return [
            FieldContribution(
                field="phone",
                value="+44 20 1234 5678",
                license="CC0",
                confidence=0.7,
            )
        ]


class FakeOverBudgetAdapter:
    """Adapter that is already over its free-tier cap."""
    meta = SourceMeta(
        key="fake_over_budget",
        name="Fake Over Budget",
        type="enrichment",
        url="https://example.com",
        license="CC0",
        terms_status="permitted",
        key_env="",
        free_tier={"cap": 5, "window": "month"},
    )

    def __init__(self):
        self.called = False

    def enrich(self, view: dict) -> list[FieldContribution]:
        self.called = True
        return []


class FakeNoFillAdapter:
    """Makes a provider call (sets api_calls_last=1) but returns no fills.

    Used to test FIX 1: budget must count API *calls*, not fills.
    Even when an adapter returns [] the invocation must still be metered.
    """
    meta = SourceMeta(
        key="fake_no_fill",
        name="Fake No Fill",
        type="enrichment",
        url="https://example.com",
        license="CC0",
        terms_status="permitted",
        key_env="",
        free_tier={"cap": 1, "window": "month"},
    )

    def __init__(self):
        self.call_count = 0

    def enrich(self, view: dict) -> list[FieldContribution]:
        self.call_count += 1
        self.api_calls_last = 1  # simulates hitting the provider
        return []


# ---------------------------------------------------------------------------
# (a) Over-budget adapter is skipped
# ---------------------------------------------------------------------------

def test_over_budget_adapter_is_skipped(session):
    """An adapter whose cap is already exhausted must not have enrich() called."""
    from app.adapters.waterfall import run_enrichment

    adapter = FakeOverBudgetAdapter()
    cap = adapter.meta.free_tier["cap"]
    # Pre-exhaust the budget
    record_use(session, "fake_over_budget", cap=cap, n=cap)

    lead = _make_lead(session)
    result = run_enrichment(session, lead, [adapter])

    # enrich() must not have been called
    assert adapter.called is False
    # No fills from this adapter
    assert result.get("fake_over_budget", 0) == 0


# ---------------------------------------------------------------------------
# (b) Missing email is filled, provenance stamped, use recorded
# ---------------------------------------------------------------------------

def test_fills_missing_email_and_stamps_provenance(session):
    """An adapter filling public_email on a lead missing it must stamp provenance."""
    from app.adapters.waterfall import run_enrichment
    from app.adapters.budget import remaining

    lead = _make_lead(session, public_email="")
    adapter = FakeEmailAdapter()

    result = run_enrichment(session, lead, [adapter])

    # One fill was recorded
    assert result.get("fake_email_src", 0) == 1

    # The lead now carries the email
    session.refresh(lead)
    assert lead.public_email == "info@testbiz.com"

    # Provenance was stamped
    prov = json.loads(lead.field_provenance_json)
    assert "public_email" in prov
    assert prov["public_email"]["source"] == "Fake Email Source"
    assert prov["public_email"]["license"] == "CC0"
    assert "at" in prov["public_email"]

    # Budget was decremented
    cap = adapter.meta.free_tier["cap"]
    assert remaining(session, "fake_email_src", cap=cap) == cap - 1


# ---------------------------------------------------------------------------
# (d) No-fill adapter still records use (FIX 1: count calls not fills)
# ---------------------------------------------------------------------------

def test_no_fill_adapter_still_records_use(session):
    """An adapter that makes a provider call but yields no fills STILL records 1 use.

    This is the core fix: Hunter returning only personal emails (discarded → [])
    consumed a real API call, so budget must advance even when fill_count == 0.
    """
    from app.adapters.waterfall import run_enrichment
    from app.adapters.budget import remaining

    adapter = FakeNoFillAdapter()
    lead = _make_lead(session)

    result = run_enrichment(session, lead, [adapter])

    # enrich() was called
    assert adapter.call_count == 1
    # No fills — fill count is 0
    assert result.get("fake_no_fill", -1) == 0
    # Budget was consumed: cap=1, used=1 → remaining=0
    cap = adapter.meta.free_tier["cap"]
    assert remaining(session, "fake_no_fill", cap=cap) == 0


def test_budget_exhausted_by_no_fill_skips_next_invocation(session):
    """After a no-fill call exhausts cap=1, the next invocation is skipped.

    Proves the free-tier is actually bounded even when adapters make calls
    that return no usable data.
    """
    from app.adapters.waterfall import run_enrichment

    adapter = FakeNoFillAdapter()
    lead1 = _make_lead(session)
    lead2 = _make_lead(session)

    # First call: enrich() is invoked and consumes the only budget slot
    run_enrichment(session, lead1, [adapter])
    assert adapter.call_count == 1

    # Second call: cap=1 is exhausted → would_exceed → enrich() NOT called
    run_enrichment(session, lead2, [adapter])
    assert adapter.call_count == 1  # still 1, not called again


# ---------------------------------------------------------------------------
# (c) Verified phone is NOT overwritten
# ---------------------------------------------------------------------------

def test_verified_phone_not_overwritten(session):
    """A lead with a validated phone must not be overwritten by enrichment."""
    from app.adapters.waterfall import run_enrichment

    verified_phone = "+44 20 7946 0958"
    validation = {
        "phone": {
            "present": True,
            "validated": True,
            "line_type": "fixed_line",
            "tier": "validated",
        }
    }
    lead = _make_lead(
        session,
        phone=verified_phone,
        validation_json=json.dumps(validation),
    )

    adapter = FakePhoneAdapter()
    result = run_enrichment(session, lead, [adapter])

    # No fills
    assert result.get("fake_phone_src", 0) == 0

    # Phone is unchanged
    session.refresh(lead)
    assert lead.phone == verified_phone
