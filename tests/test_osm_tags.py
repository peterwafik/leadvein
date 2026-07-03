from __future__ import annotations

from sqlmodel import Session, select

import app.leadvault as lv
from app.adapters.osm_tags import load_tag_config, match_categories, seed_osm_tag_mappings
from app.core.db import LeadCategory


def test_allowlist_and_alias_mapping():
    assert match_categories({"amenity": "restaurant"}) == ["restaurant"]
    assert match_categories({"amenity": "fast_food"}) == ["takeaway"]
    assert match_categories({"shop": "hairdresser"}) == ["hair_salon"]


def test_wildcard_maps_unknown_values():
    assert match_categories({"shop": "fishing"}) == ["fishing"]
    assert match_categories({"craft": "electrician"}) == ["electrician"]
    assert match_categories({"office": "architect"}) == ["architect"]


def test_exclusions_and_non_business():
    assert match_categories({"shop": "vacant"}) == []
    assert match_categories({"office": "government"}) == []
    assert match_categories({"amenity": "bench"}) == []
    assert match_categories({"highway": "bus_stop"}) == []


def test_multi_tag_collects_all():
    cats = match_categories({"amenity": "cafe", "shop": "bakery"})
    assert set(cats) == {"cafe", "bakery"}


def test_seed_idempotent_and_registers_categories():
    # Adaptation from brief: _seed_accounts() runs at leadvault import time (same
    # pattern as test_georef.py — n1 may already be 0 if startup pre-seeded).
    # Verify the DB count directly so the assertion is import-order-independent.
    from sqlmodel import select
    from app.core.db import CategoryMapping
    with Session(lv.engine) as s:
        n1 = seed_osm_tag_mappings(s)
        n2 = seed_osm_tag_mappings(s)
        assert n2 == 0
        count = len(s.exec(
            select(CategoryMapping).where(CategoryMapping.source_key == "osm")
        ).all())
        assert count >= 40           # allowlist+alias entries land in CategoryMapping
        assert n1 in (0, count)      # 0 if app startup already seeded
