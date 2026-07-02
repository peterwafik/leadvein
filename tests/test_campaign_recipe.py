"""Task 5: online_ordering campaign → web.runs_tech composition."""
from app.core.db import init_db
from app.campaigns.seed import seed_campaigns
from app.campaigns.crud import get_by_key
from app.campaigns.compile import compile_campaign


def _session():
    e = init_db("sqlite://")
    from sqlmodel import Session
    return Session(e)


def test_online_ordering_nodes():
    with _session() as s:
        seed_campaigns(s)
        campaign = get_by_key(s, "online_ordering")
        assert campaign is not None, "online_ordering campaign not seeded"

        out = compile_campaign(campaign, {"area": "Oxford"})
        nodes = out["composition"]["nodes"]

        # Must include web.runs_tech targeting GloriaFood + ChowNow
        assert {
            "predicate": "web.runs_tech",
            "params": {"recipe_in": ["gloriafood", "chownow"], "min_strength": 1},
        } in nodes, f"web.runs_tech node missing from {nodes}"

        # Must include geo.city with the substituted area
        assert {
            "predicate": "geo.city",
            "params": {"value": "Oxford"},
        } in nodes, f"geo.city node missing from {nodes}"

        # Must include contactability node
        assert {
            "predicate": "contactability.has_business_contact",
            "params": {},
        } in nodes, f"contactability node missing from {nodes}"

        # INV-6: no gated notices
        assert out["gated_notices"] == [], f"unexpected gated_notices: {out['gated_notices']}"

        # INV-8: no OSM category pin — this campaign targets by tech, not taxonomy
        assert not any("category" in n["predicate"] for n in nodes), (
            f"INV-8 violated: category predicate found in {nodes}"
        )

        # Quality profile
        assert out["quality_profile_key"] == "baseline"


def test_shopify_uk_nodes():
    with _session() as s:
        seed_campaigns(s)
        campaign = get_by_key(s, "shopify_uk")
        assert campaign is not None, "shopify_uk campaign not seeded"

        out = compile_campaign(campaign, {})
        nodes = out["composition"]["nodes"]

        assert {
            "predicate": "web.runs_tech",
            "params": {"recipe_in": ["shopify"], "min_strength": 1},
        } in nodes, f"web.runs_tech (shopify) node missing from {nodes}"

        assert {
            "predicate": "geo.country",
            "params": {"value": "GB"},
        } in nodes, f"geo.country node missing from {nodes}"

        assert {
            "predicate": "contactability.has_business_contact",
            "params": {},
        } in nodes, f"contactability node missing from {nodes}"

        assert out["gated_notices"] == []
        assert not any("category" in n["predicate"] for n in nodes)
        assert out["quality_profile_key"] == "baseline"


def test_seed_idempotent():
    """seed_campaigns is idempotent — calling it twice should not raise."""
    with _session() as s:
        c1 = seed_campaigns(s)
        c2 = seed_campaigns(s)
        assert c1 == c2
        assert get_by_key(s, "online_ordering") is not None
        assert get_by_key(s, "shopify_uk") is not None
