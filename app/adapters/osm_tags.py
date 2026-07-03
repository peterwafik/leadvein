"""OSM business-tag taxonomy — CONFIG, not code (spec §2).

The committed JSON defines which OSM tags are business-bearing and how they
map to taxonomy category keys. Wildcard keys (shop/office/craft/healthcare)
derive categories from tag values minus exclusions; allowlist keys
(amenity/tourism/leisure) map only curated business values. Adding a business
class later = config edit, zero code.

Signature adaptations vs brief:
- upsert_category(session, key, label) matches the real signature exactly
  (app/core/taxonomy.py:27 — positional args session, key, label; parent_key optional).
- CategoryMapping columns (source_key, external_value, category_key) match
  app/core/db.py:53 exactly; no adaptation needed.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "data", "osm_business_tags.json")
_KEY_ORDER = ("shop", "amenity", "office", "craft", "healthcare", "tourism", "leisure")


@lru_cache(maxsize=1)
def load_tag_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")


def match_categories(tags: dict, config: dict | None = None) -> list[str]:
    """Return taxonomy category keys for an OSM element's tags.

    Precedence follows _KEY_ORDER; all matched categories are collected (a
    business may legitimately carry multiple categories). Returns [] when no
    business match is found.
    """
    config = config or load_tag_config()
    out: list[str] = []
    for key in _KEY_ORDER:
        rule = config.get(key)
        value = (tags or {}).get(key)
        if not rule or not value:
            continue
        if rule["mode"] == "allowlist":
            cat = rule["map"].get(value)
        else:  # wildcard
            if value in rule.get("exclude", []):
                cat = None
            else:
                cat = rule.get("alias", {}).get(value) or _slug(value)
        if cat and cat not in out:
            out.append(cat)
    return out


def seed_osm_tag_mappings(session) -> int:
    """Idempotent upsert of explicit (allowlist + alias) entries into
    CategoryMapping (source_key='osm'). Wildcards resolve at match time and
    are not enumerated here. Also auto-registers each mapped category in
    LeadCategory via upsert_category.

    Returns the number of *new* rows inserted (0 on a repeat call).
    """
    from sqlmodel import select
    from app.core.db import CategoryMapping
    from app.core.taxonomy import upsert_category

    config = load_tag_config()
    n = 0
    for key in _KEY_ORDER:
        rule = config.get(key) or {}
        if rule.get("mode") == "allowlist":
            entries = rule.get("map", {})
        else:
            entries = rule.get("alias", {})
        for value, cat in entries.items():
            ext = f"{key}={value}"
            exists = session.exec(
                select(CategoryMapping).where(
                    CategoryMapping.source_key == "osm",
                    CategoryMapping.external_value == ext,
                )
            ).first()
            if exists:
                continue
            session.add(
                CategoryMapping(source_key="osm", external_value=ext, category_key=cat)
            )
            upsert_category(session, cat, cat.replace("_", " ").title())
            n += 1
    session.commit()
    return n
