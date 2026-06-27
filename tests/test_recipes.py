from app.engine.recipes import (
    Recipe, BUILTIN_RECIPES, get_builtin, recipes_by_category,
)


def test_gloriafood_recipe_is_faithful():
    gf = get_builtin("gloriafood")
    assert gf is not None
    assert gf.type == "GloriaFood"
    assert gf.category == "Online Ordering / Restaurants"
    assert gf.urlscan_query == "domain:fbgcdn.com"
    assert gf.publicwww_query == '"fbgcdn.com/embedder"'
    for fp in ["fbgcdn.com", "ewm2.js", "data-glf-cuid", "data-glf-ruid", "gloriafood"]:
        assert fp in gf.verify_fingerprints
    assert set(gf.id_extractors.keys()) == {"ruid", "cuid"}
    assert "foodbooking" in gf.exclude_hosts


def test_catalog_has_expected_breadth():
    ids = {r.id for r in BUILTIN_RECIPES}
    for expected in ["gloriafood", "shopify", "calendly", "intercom", "stripe_checkout"]:
        assert expected in ids
    for r in BUILTIN_RECIPES:
        assert r.verify_fingerprints, r.id
        assert r.urlscan_query, r.id


def test_grouping_by_category():
    grouped = recipes_by_category(BUILTIN_RECIPES)
    assert "Online Ordering / Restaurants" in grouped
    assert any(r.type == "GloriaFood" for r in grouped["Online Ordering / Restaurants"])
