"""GeoRef static reference: fixture-only seeding (no network), search, countries."""
from __future__ import annotations

from sqlmodel import Session, select

import app.leadvault as lv
from app.geo.ref import GeoRef, seed_geo_fixture, list_countries, search_areas


def test_seed_geo_fixture_idempotent_and_offline():
    with Session(lv.engine) as s:
        n1 = seed_geo_fixture(s)
        n2 = seed_geo_fixture(s)          # second run inserts nothing
        assert n2 == 0
        total = len(s.exec(select(GeoRef)).all())
        assert total >= 40                # fixture has countries + GB regions + cities
        assert n1 in (0, total)           # 0 if app startup already seeded


def test_countries_include_zero_coverage_ones():
    with Session(lv.engine) as s:
        seed_geo_fixture(s)
        codes = {c.country_code for c in list_countries(s)}
        # Complete country layer: places with no inventory are still findable
        assert {"GB", "US", "DE", "FR"} <= codes
        names = {c.country_name for c in list_countries(s)}
        assert "United Kingdom" in names


def test_search_areas_finds_oxford_ranked():
    with Session(lv.engine) as s:
        seed_geo_fixture(s)
        rows = search_areas(s, "GB", "oxf")
        names = [r.name for r in rows]
        assert "Oxford" in names
        ox = next(r for r in rows if r.name == "Oxford")
        assert ox.kind == "city"
        assert ox.admin1_name == "England"
        assert ox.admin2_name == "Oxfordshire"
        # region rows are searchable too
        regs = search_areas(s, "GB", "oxfordshire")
        assert any(r.kind == "region" and r.name == "Oxfordshire" for r in regs)


def test_search_areas_empty_query_returns_top_population():
    with Session(lv.engine) as s:
        seed_geo_fixture(s)
        rows = search_areas(s, "GB", "")
        assert rows, "empty query lists top areas"
        cities = [r for r in rows if r.kind == "city"]
        assert cities == sorted(cities, key=lambda r: -r.population)
