# tests/test_find_sentence.py
from __future__ import annotations

from sqlmodel import Session

import app.leadvault as lv
from app.campaigns.assemble import assemble_composition
from app.campaigns.sentence import render_sentence


def _s():
    return Session(lv.engine)


def test_sentence_full_campaign():
    comp = assemble_composition({
        "cities": ["Oxford", "Cambridge"], "categories": ["restaurant", "cafe"],
        "tech_recipes": ["gloriafood"], "min_strength": 1,
        "contact_channel": "phone", "freshness_days": 30})
    with _s() as s:
        text = render_sentence(s, comp, quality_profile_keys=["phone_validated"])
    assert text.startswith("We'll find")
    assert "restaurant" in text and "cafe" in text
    assert "GloriaFood" in text                      # label from recipe library
    assert "Oxford or Cambridge" in text
    assert "validated phone" in text
    assert "30 days" in text


def test_sentence_renders_from_composition_not_input():
    """Drift guard: the sentence reflects the COMPILED composition."""
    comp = assemble_composition({"cities": ["Oxford"], "categories": ["bakery"]})
    comp["nodes"] = [n for n in comp["nodes"] if n["predicate"] != "category.any"]
    with _s() as s:
        text = render_sentence(s, comp)
    assert "bakery" not in text                      # dropped node → dropped words


def test_sentence_whole_country_and_unknown_predicates():
    comp = assemble_composition({"whole_countries": ["GB"]})
    comp["nodes"].append({"predicate": "web.is_enriched", "params": {}})
    comp["nodes"].append({"predicate": "source.type", "params": {"value": "open_data"},
                          "negate": True})
    with _s() as s:
        text = render_sentence(s, comp)
    assert "United Kingdom" in text                  # name via geo_ref, not "GB"
    assert "2 advanced condition" in text


def test_sentence_empty_composition():
    with _s() as s:
        text = render_sentence(s, {"op": "AND", "nodes": []})
    assert text == "We'll find all available business leads."
