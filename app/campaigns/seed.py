from __future__ import annotations

import json

from sqlmodel import Session

from app.campaigns.crud import create_campaign, get_by_key

# ---------------------------------------------------------------------------
# Campaign definitions — all vertical / financial vocabulary lives here,
# NEVER in app/core (grep gate: test_campaign_grepclean.py).
# ---------------------------------------------------------------------------

_CAMPAIGNS = [
    {
        "key": "utilities_uk",
        "name": "Utilities (UK)",
        "description": "UK utilities leads — covers all business types across the sector.",
        "quality_profile_key": "utilities",
        "scoring_profile_key": "utility_energy",
        "gated_signals": [],
        "param_schema": {
            "area": {
                "type": "city",
                "label": "Area",
                "help": "A UK town or city",
            }
        },
        "composition_template": {
            "op": "AND",
            "nodes": [
                {"predicate": "geo.country", "params": {"value": "GB"}},
                {"predicate": "geo.city", "params": {"value": "{area}"}},
                {"predicate": "contactability.has_business_contact", "params": {}},
            ],
        },
    },
    {
        "key": "online_ordering",
        "name": "Online ordering upgrades",
        "description": (
            "Restaurants running GloriaFood or ChowNow — "
            "a proven ground-truth signal for online-ordering intent. "
            "Targets by detected platform, not business category."
        ),
        "quality_profile_key": "baseline",
        "scoring_profile_key": "",
        "gated_signals": [],
        "param_schema": {
            "area": {
                "type": "city",
                "label": "Area",
                "help": "A UK town or city (optional)",
            }
        },
        "composition_template": {
            "op": "AND",
            "nodes": [
                {
                    "predicate": "web.runs_tech",
                    "params": {"recipe_in": ["gloriafood", "chownow"], "min_strength": 1},
                },
                {"predicate": "geo.city", "params": {"value": "{area}"}},
                {"predicate": "contactability.has_business_contact", "params": {}},
            ],
        },
    },
    {
        "key": "shopify_uk",
        "name": "Shopify stores (UK)",
        "description": (
            "UK businesses running Shopify — "
            "identified via detected platform — not limited to a specific business category."
        ),
        "quality_profile_key": "baseline",
        "scoring_profile_key": "",
        "gated_signals": [],
        "param_schema": {},
        "composition_template": {
            "op": "AND",
            "nodes": [
                {
                    "predicate": "web.runs_tech",
                    "params": {"recipe_in": ["shopify"], "min_strength": 1},
                },
                {"predicate": "geo.country", "params": {"value": "GB"}},
                {"predicate": "contactability.has_business_contact", "params": {}},
            ],
        },
    },
    {
        "key": "business_restructuring",
        "name": "Business Restructuring",
        "description": (
            "Businesses in financial distress / restructuring. "
            "Gated financial + size signals are shown but require a licensed data source to activate."
        ),
        "quality_profile_key": "baseline",
        "scoring_profile_key": "",
        "gated_signals": [
            "attributes.size_band",
            "attributes.has_mca",
            "attributes.amount_owed",
            "attributes.lender",
        ],
        "param_schema": {
            "area": {
                "type": "city",
                "label": "Area",
                "help": "A UK town or city",
            },
            "sectors": {
                "type": "list",
                "label": "Business types",
            },
        },
        "composition_template": {
            "op": "AND",
            "nodes": [
                {"predicate": "category.any", "params": {"in": ["{sectors}"]}},
                {"predicate": "geo.city", "params": {"value": "{area}"}},
                {"predicate": "contactability.has_business_contact", "params": {}},
            ],
        },
    },
]


def seed_campaigns(session: Session) -> int:
    """Upsert the two built-in campaigns. Idempotent; returns count of known campaigns."""
    for defn in _CAMPAIGNS:
        existing = get_by_key(session, defn["key"])
        if existing is None:
            create_campaign(
                session,
                key=defn["key"],
                name=defn["name"],
                description=defn["description"],
                composition_template=defn["composition_template"],
                preferred=[],
                scoring_profile_key=defn["scoring_profile_key"],
                quality_profile_key=defn["quality_profile_key"],
                gated_signals=defn["gated_signals"],
                param_schema=defn["param_schema"],
                active=True,
            )
        else:
            # Idempotent: update mutable fields in case defaults changed.
            existing.name = defn["name"]
            existing.description = defn["description"]
            existing.composition_template = json.dumps(defn["composition_template"])
            existing.scoring_profile_key = defn["scoring_profile_key"]
            existing.quality_profile_key = defn["quality_profile_key"]
            existing.gated_signals = json.dumps(defn["gated_signals"])
            existing.param_schema = json.dumps(defn["param_schema"])
            session.add(existing)
            session.commit()
    return len(_CAMPAIGNS)
