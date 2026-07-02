"""prefill_answers — generic walk of a campaign's composition_template back into
builder answers (INV-8: reads only the row; no per-campaign strings here).
Unfilled "{placeholders}" become empty answers the buyer fills in the builder."""
from __future__ import annotations

import json


def _is_placeholder(v) -> bool:
    return isinstance(v, str) and v.startswith("{") and v.endswith("}") and len(v) > 2


def _clean_list(values) -> list[str]:
    return [v for v in (values or []) if isinstance(v, str) and not _is_placeholder(v)]


def prefill_answers(campaign) -> dict:
    answers = {"whole_countries": [], "regions": [], "cities": [],
               "categories": [], "tech_recipes": [], "min_strength": 1,
               "contact_channel": "", "min_quality": 0, "freshness_days": 0}
    template = json.loads(campaign.composition_template or "{}")

    def walk(node: dict) -> None:
        if "op" in node:
            for n in node.get("nodes", []):
                walk(n)
            return
        pred = node.get("predicate", "")
        params = node.get("params", {}) or {}
        if pred == "geo.country" and not _is_placeholder(params.get("value")):
            answers["whole_countries"].append(params.get("value", ""))
        elif pred == "geo.country_any":
            answers["whole_countries"] += _clean_list(params.get("in"))
        elif pred in ("geo.city", "geo.region"):
            key = "cities" if pred == "geo.city" else "regions"
            if not _is_placeholder(params.get("value")) and params.get("value"):
                answers[key].append(params["value"])
        elif pred == "geo.city_any":
            answers["cities"] += _clean_list(params.get("in"))
        elif pred == "geo.region_any":
            answers["regions"] += _clean_list(params.get("in"))
        elif pred == "category.any":
            answers["categories"] += _clean_list(params.get("in"))
        elif pred == "web.runs_tech":
            answers["tech_recipes"] += _clean_list(params.get("recipe_in"))
            answers["min_strength"] = int(params.get("min_strength") or 1)
        elif pred == "contactability.has_phone":
            answers["contact_channel"] = "phone"
        elif pred == "contactability.has_role_email":
            answers["contact_channel"] = "email"
        elif pred == "contactability.has_business_contact":
            answers["contact_channel"] = "either"
        elif pred == "quality.min_score" and not _is_placeholder(params.get("min")):
            answers["min_quality"] = int(params.get("min") or 0)
        elif pred == "freshness.verified_within" and not _is_placeholder(params.get("days")):
            answers["freshness_days"] = int(params.get("days") or 0)

    walk(template)
    for k in ("whole_countries", "regions", "cities", "categories", "tech_recipes"):
        answers[k] = [x for x in dict.fromkeys(answers[k]) if x]   # dedupe, keep order
    return answers
