from __future__ import annotations

import json

from sqlmodel import Session

import app.leadvault as lv
from app.campaigns.assemble import assemble_composition, channel_profile_key
from app.campaigns.crud import get_by_key
from app.campaigns.prefill import prefill_answers


def _preds(comp):
    out = []
    def walk(node):
        if "op" in node:
            for n in node.get("nodes", []):
                walk(n)
        else:
            out.append(node["predicate"])
    walk(comp)
    return out


def test_assemble_full_answers():
    comp = assemble_composition({
        "cities": ["Oxford", "Cambridge"], "regions": [],
        "whole_countries": [], "categories": ["restaurant", "cafe"],
        "tech_recipes": ["gloriafood"], "min_strength": 2,
        "contact_channel": "phone", "min_quality": 70, "freshness_days": 30})
    assert comp["op"] == "AND"
    preds = _preds(comp)
    assert "geo.city_any" in preds and "category.any" in preds
    assert "web.runs_tech" in preds and "contactability.has_phone" in preds
    assert "quality.min_score" in preds and "freshness.verified_within" in preds
    tech = next(n for n in comp["nodes"] if n.get("predicate") == "web.runs_tech")
    assert tech["params"] == {"recipe_in": ["gloriafood"], "min_strength": 2}


def test_assemble_mixed_geo_is_or_group():
    comp = assemble_composition({"whole_countries": ["US"], "cities": ["Oxford"],
                                 "regions": [], "categories": [], "tech_recipes": []})
    or_groups = [n for n in comp["nodes"] if n.get("op") == "OR"]
    assert or_groups, "country scope + specific areas must OR together"
    inner = _preds(or_groups[0])
    assert "geo.country_any" in inner and "geo.city_any" in inner


def test_assemble_empty_answers_is_empty_and():
    assert assemble_composition({}) == {"op": "AND", "nodes": []}


def test_channel_profile_key():
    assert channel_profile_key("phone") == "phone_validated"
    assert channel_profile_key("email") == "email_validated"
    assert channel_profile_key("either") == "contact_validated"
    assert channel_profile_key("") == ""


def test_prefill_online_ordering_campaign():
    with Session(lv.engine) as s:
        camp = get_by_key(s, "online_ordering")
    a = prefill_answers(camp)
    assert set(a["tech_recipes"]) == {"gloriafood", "chownow"}
    assert a["contact_channel"] == "either"
    assert a["cities"] == []          # "{area}" placeholder → empty, user fills it


def test_prefill_is_generic_roundtrip():   # INV-8 guard: prefill→assemble covers template intent
    with Session(lv.engine) as s:
        camp = get_by_key(s, "shopify_uk")
    a = prefill_answers(camp)
    assert a["whole_countries"] == ["GB"]
    comp = assemble_composition(a)
    assert "web.runs_tech" in _preds(comp) and "geo.country_any" in _preds(comp)
