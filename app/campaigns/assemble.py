"""assemble_composition — the ONE path from plain-language builder answers to a
v2 composition. The review sentence renders from the OUTPUT of this function,
so what the user reads is always what runs."""
from __future__ import annotations

_CHANNEL_PRED = {"phone": "contactability.has_phone",
                 "email": "contactability.has_role_email",
                 "either": "contactability.has_business_contact"}

_CHANNEL_PROFILE = {"phone": "phone_validated",
                    "email": "email_validated",
                    "either": "contact_validated"}


def channel_profile_key(channel: str) -> str:
    return _CHANNEL_PROFILE.get(channel or "", "")


def _clean(values) -> list[str]:
    return [str(v).strip() for v in (values or []) if str(v).strip()]


def assemble_composition(answers: dict) -> dict:
    nodes: list[dict] = []

    countries = _clean(answers.get("whole_countries"))
    regions = _clean(answers.get("regions"))
    cities = _clean(answers.get("cities"))
    area_nodes: list[dict] = []
    if regions:
        area_nodes.append({"predicate": "geo.region_any", "params": {"in": regions}})
    if cities:
        area_nodes.append({"predicate": "geo.city_any", "params": {"in": cities}})
    country_node = ({"predicate": "geo.country_any", "params": {"in": countries}}
                    if countries else None)
    if country_node and area_nodes:
        nodes.append({"op": "OR", "nodes": [country_node, *area_nodes]})
    elif country_node:
        nodes.append(country_node)
    else:
        nodes.extend(area_nodes)

    categories = _clean(answers.get("categories"))
    if categories:
        nodes.append({"predicate": "category.any", "params": {"in": categories}})

    recipes = _clean(answers.get("tech_recipes"))
    if recipes:
        nodes.append({"predicate": "web.runs_tech",
                      "params": {"recipe_in": recipes,
                                 "min_strength": int(answers.get("min_strength") or 1)}})

    pred = _CHANNEL_PRED.get(answers.get("contact_channel") or "")
    if pred:
        nodes.append({"predicate": pred, "params": {}})

    if int(answers.get("min_quality") or 0) > 0:
        nodes.append({"predicate": "quality.min_score",
                      "params": {"min": int(answers["min_quality"])}})
    if int(answers.get("freshness_days") or 0) > 0:
        nodes.append({"predicate": "freshness.verified_within",
                      "params": {"days": int(answers["freshness_days"])}})
    return {"op": "AND", "nodes": nodes}
