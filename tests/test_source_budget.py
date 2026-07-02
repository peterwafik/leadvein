"""Tests for per-source credit budget and per-field provenance.

Step 1 (TDD): tests written before implementation so they fail red first.
"""
from __future__ import annotations

import json

import pytest
from sqlmodel import Session

from app.core.db import init_db, Lead


@pytest.fixture()
def session():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        yield s


# ---------------------------------------------------------------------------
# record_use / remaining / would_exceed
# ---------------------------------------------------------------------------

def test_record_use_accumulates(session):
    from app.adapters.budget import record_use

    used1 = record_use(session, "src_a", cap=10, n=3)
    assert used1 == 3

    used2 = record_use(session, "src_a", cap=10, n=2)
    assert used2 == 5


def test_remaining_decrements(session):
    from app.adapters.budget import record_use, remaining

    record_use(session, "src_b", cap=20, n=7)
    assert remaining(session, "src_b", cap=20) == 13


def test_would_exceed_true_at_cap(session):
    from app.adapters.budget import record_use, would_exceed

    record_use(session, "src_c", cap=5, n=5)
    # used == cap → requesting 1 more should exceed
    assert would_exceed(session, "src_c", cap=5, n=1) is True


def test_would_exceed_true_over_cap(session):
    from app.adapters.budget import record_use, would_exceed

    record_use(session, "src_d", cap=5, n=4)
    # used=4, cap=5, requesting n=2 → 4+2=6 > 5 → True
    assert would_exceed(session, "src_d", cap=5, n=2) is True


def test_would_exceed_false_under_cap(session):
    from app.adapters.budget import record_use, would_exceed

    record_use(session, "src_e", cap=10, n=3)
    # used=3, cap=10, requesting n=1 → 3+1=4 <= 10 → False
    assert would_exceed(session, "src_e", cap=10, n=1) is False


def test_remaining_zero_when_at_cap(session):
    from app.adapters.budget import record_use, remaining

    record_use(session, "src_f", cap=5, n=5)
    assert remaining(session, "src_f", cap=5) == 0


def test_remaining_zero_clamped_when_over_cap(session):
    """remaining must never go negative."""
    from app.adapters.budget import record_use, remaining

    # Force over-cap (e.g. cap was raised then lowered)
    record_use(session, "src_g", cap=10, n=8)
    # Now query with a lower cap
    assert remaining(session, "src_g", cap=5) == 0


# ---------------------------------------------------------------------------
# stamp_provenance
# ---------------------------------------------------------------------------

def test_stamp_provenance_writes_nested_structure():
    from app.adapters.budget import stamp_provenance

    lead = Lead()
    stamp_provenance(lead, "phone", "src_h", "ODbL")

    data = json.loads(lead.field_provenance_json)
    assert "phone" in data
    entry = data["phone"]
    assert entry["source"] == "src_h"
    assert entry["license"] == "ODbL"
    assert "at" in entry  # timestamp present


def test_stamp_provenance_round_trips_via_json():
    from app.adapters.budget import stamp_provenance

    lead = Lead()
    stamp_provenance(lead, "website_url", "src_i", "CC-BY-4.0")

    # Re-parse the JSON to verify it is valid and round-trips
    raw = lead.field_provenance_json
    parsed = json.loads(raw)
    assert parsed["website_url"]["source"] == "src_i"
    assert parsed["website_url"]["license"] == "CC-BY-4.0"

    # Serialize again and re-parse — must be stable
    reparsed = json.loads(json.dumps(parsed))
    assert reparsed == parsed


def test_stamp_provenance_overwrites_existing_field():
    from app.adapters.budget import stamp_provenance

    lead = Lead()
    stamp_provenance(lead, "phone", "old_src", "ODbL")
    stamp_provenance(lead, "phone", "new_src", "MIT")

    data = json.loads(lead.field_provenance_json)
    assert data["phone"]["source"] == "new_src"
    assert data["phone"]["license"] == "MIT"


def test_stamp_provenance_preserves_other_fields():
    from app.adapters.budget import stamp_provenance

    lead = Lead()
    stamp_provenance(lead, "phone", "src_j", "ODbL")
    stamp_provenance(lead, "website_url", "src_k", "CC-BY")

    data = json.loads(lead.field_provenance_json)
    assert "phone" in data
    assert "website_url" in data


def test_lead_field_provenance_json_default():
    """Lead.field_provenance_json defaults to '{}'."""
    lead = Lead()
    assert lead.field_provenance_json == "{}"
    assert json.loads(lead.field_provenance_json) == {}
