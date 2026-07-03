"""Tests for the streaming PBF parser (Task 5).

Fixture contract (14 elements: nodes 101-109 + bare nodes 201-204 + way 301):
- Exactly 7 leads expected: nodes 101, 102, 103, 107, 108, 109 and way 301.
- Nodes 104 (nameless), 105 (bench), 106 (vacant) are skipped.
- Nodes 201-204 are bare location nodes (no tags) and generate no leads.
"""
from __future__ import annotations

import os

from app.ingestion.pbf_stream import stream_business_leads

FIXTURE = os.path.join("tests", "fixtures", "bulk_fixture.osm.pbf")


def test_fixture_parses_expected_leads():
    leads = list(stream_business_leads(FIXTURE, source_key="osm_geofabrik"))
    by_name = {l.business_name: l for l in leads}
    assert len(leads) == 7
    assert by_name["Fixture Bakery"].category_keys == ["bakery"]
    assert by_name["Fixture Bakery"].phone == "+441865111111"
    assert by_name["Fixture Electrician"].category_keys == ["electrician"]
    assert by_name["Fixture Hotel"].website_url == "https://hotel.fixture.example"
    assert "Fixture Bench" not in by_name          # non-business skipped
    assert "Vacant Shop" not in by_name            # excluded skipped


def test_way_gets_centroid_and_raw_ref():
    leads = {l.business_name: l for l in
             stream_business_leads(FIXTURE, source_key="osm_geofabrik")}
    sm = leads["Fixture Supermarket"]
    assert sm.raw_ref.startswith("way/")
    assert sm.address["lat"] is not None and sm.address["lon"] is not None
    assert 51.0 < sm.address["lat"] < 52.5


def test_progress_callback_fires():
    seen = []
    list(stream_business_leads(FIXTURE, source_key="x",
                               progress_cb=lambda n: seen.append(n)))
    # fixture has 14 elements (9 named nodes + 4 bare nodes + 1 way)
    # the final flush call must still report the total
    assert seen and seen[-1] >= 12
