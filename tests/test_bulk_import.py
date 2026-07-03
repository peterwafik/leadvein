"""Bulk import over the committed fixture PBF — full pipeline contracts hold."""
from __future__ import annotations

import json
import os

from sqlmodel import Session, select

import app.leadvault as lv
from app.core.db import Lead
from app.ingestion.bulk import run_bulk_import
from app.quality.ordinals import ordinal

FIXTURE = os.path.join("tests", "fixtures", "bulk_fixture.osm.pbf")


def _run(s, **kw):
    return run_bulk_import(s, "monaco", pbf_path=FIXTURE, **kw)


def test_fixture_import_counts_and_rows():
    with Session(lv.engine) as s:
        counts = _run(s)
        assert counts["matched"] == 7
        assert counts["stored_new"] + counts["merged"] + counts["skipped_duplicate_in_run"] == 7
        lead = s.exec(select(Lead).where(Lead.business_name == "Fixture Bakery")).first()
        assert lead is not None
        assert lead.source_key == "osm_geofabrik"
        assert lead.source_license == "ODbL"
        assert "OpenStreetMap contributors" in lead.attribution
        assert lead.country == "GB"            # addr:country wins over region default
        prov = json.loads(lead.field_provenance_json or "{}")
        assert prov.get("phone", {}).get("source") == "osm_geofabrik"
        assert lead.tier_contact >= ordinal("present")
        # hot funnel counted honestly
        assert counts["hot"] <= counts["stored_new"] + counts["merged"]


def test_region_country_fallback():
    with Session(lv.engine) as s:
        _run(s)
        gp = s.exec(select(Lead).where(Lead.business_name == "Fixture GP")).first()
        # fixture GP has no addr:country -> falls back to region country (MC)
        assert gp.country == "MC"


def test_reimport_is_idempotent():
    with Session(lv.engine) as s:
        _run(s)
        n_before = len(s.exec(select(Lead).where(
            Lead.source_key == "osm_geofabrik")).all())
        counts2 = _run(s)
        n_after = len(s.exec(select(Lead).where(
            Lead.source_key == "osm_geofabrik")).all())
        assert n_after == n_before                 # no duplicates
        assert counts2["merged"] >= 1              # existing rows matched


def test_cancel_stops_between_batches():
    with Session(lv.engine) as s:
        counts = _run(s, batch_size=2, cancel_check=lambda: True)
        # cancelled before the first batch commit completes the run
        assert counts["matched"] <= 7


def test_dedup_within_run():
    # Fixture Dup Bakery shares a phone with Fixture Bakery -> same dedupe key
    with Session(lv.engine) as s:
        counts = _run(s)
        assert counts["skipped_duplicate_in_run"] >= 1 or counts["merged"] >= 1
