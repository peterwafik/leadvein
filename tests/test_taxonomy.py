from sqlmodel import Session
from app.core.db import init_db
from app.core.taxonomy import (seed_taxonomy, all_categories, category_by_key,
                               add_mapping, categories_for_external, upsert_category)


def test_seed_is_idempotent_and_generic():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        seed_taxonomy(s)
        seed_taxonomy(s)
        keys = [c["key"] for c in all_categories(s)]
        assert keys.count("restaurant") == 1
        assert "gym" in keys and "cafe" in keys
        # taxonomy must be generic — no vertical assumptions baked in
        joined = " ".join(keys).lower()
        assert "energy" not in joined and "utility" not in joined


def test_mapping_resolves_external_to_category_keys():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        seed_taxonomy(s)
        add_mapping(s, "src", "amenity=restaurant", "restaurant")
        assert categories_for_external(s, "src", "amenity=restaurant") == ["restaurant"]
        assert categories_for_external(s, "src", "amenity=unknown") == []
        assert category_by_key(s, "restaurant").label == "Restaurant"
