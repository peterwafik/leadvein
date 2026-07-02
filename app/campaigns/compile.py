"""compile_campaign — generic transform: Campaign row + buyer params -> v2 composition + gated notices.

INV-6: gated_signals paths are NEVER added to the composition JSON.
INV-8: this module contains no per-campaign strings; it reads only the row + params.
"""
from __future__ import annotations

import copy
import json
from typing import Any


def _substitute(value: Any, params: dict) -> Any:
    """Recursively substitute ``"{key}"`` placeholders in a template structure.

    Rules
    -----
    - A string exactly equal to ``"{key}"`` is replaced with ``params[key]``.
    - A list whose *only* element is a single-placeholder string ``"{key}"`` where
      ``params[key]`` is itself a list is replaced by that list (list-slot expansion).
    - Dicts and lists are traversed recursively.
    """
    if isinstance(value, str):
        # Exact-match replacement: "{key}" -> params[key]
        if value.startswith("{") and value.endswith("}") and len(value) > 2:
            key = value[1:-1]
            if key in params:
                return params[key]
        return value

    if isinstance(value, list):
        # List-slot expansion: ["{sectors}"] -> params["sectors"] when it's a list
        if (
            len(value) == 1
            and isinstance(value[0], str)
            and value[0].startswith("{")
            and value[0].endswith("}")
            and len(value[0]) > 2
        ):
            key = value[0][1:-1]
            if key in params and isinstance(params[key], list):
                return list(params[key])
        # Otherwise substitute element-by-element
        return [_substitute(item, params) for item in value]

    if isinstance(value, dict):
        return {k: _substitute(v, params) for k, v in value.items()}

    return value


def _has_unfilled_placeholder(value: Any) -> bool:
    """Return True if any string in *value* is still an unfilled ``"{...}"`` placeholder."""
    if isinstance(value, str):
        return value.startswith("{") and value.endswith("}") and len(value) > 2
    if isinstance(value, list):
        return any(_has_unfilled_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(_has_unfilled_placeholder(v) for v in value.values())
    return False


def compile_campaign(campaign, buyer_params: dict) -> dict:
    """Compile *campaign* with *buyer_params* into a ready-to-evaluate composition.

    Parameters
    ----------
    campaign:
        A ``Campaign`` ORM row whose JSON columns are raw strings.
    buyer_params:
        Key/value pairs supplied by the buyer (e.g. ``{"area": "Oxford", "sectors": [...]}``)

    Returns
    -------
    dict with keys:
        composition          — v2 ``{"op":"AND","nodes":[...]}`` with placeholders substituted
        scoring_profile_key  — from the campaign row
        quality_profile_key  — from the campaign row
        preferred            — parsed list from the campaign row
        gated_notices        — list of ``{"path": str, "reason": "requires licensed source"}``
                               one per gated signal; NEVER appear in composition (INV-6)
    """
    # Parse JSON columns (they are stored as raw strings)
    template: dict = json.loads(campaign.composition_template)
    preferred: list = json.loads(campaign.preferred)
    gated_signals: list[str] = json.loads(campaign.gated_signals)

    # Build gated notices — these paths must NEVER appear in the composition (INV-6)
    gated_notices = [
        {"path": path, "reason": "requires licensed source"}
        for path in gated_signals
    ]

    # Deep-copy the template so we don't mutate the parsed object
    filled = copy.deepcopy(template)

    # Substitute placeholders throughout the composition template
    filled = _substitute(filled, buyer_params)

    # Drop any node whose params still contain an unfilled placeholder
    # (optional params not supplied by the buyer)
    if "nodes" in filled and isinstance(filled["nodes"], list):
        filled["nodes"] = [
            node for node in filled["nodes"]
            if not _has_unfilled_placeholder(node.get("params", {}))
        ]

    return {
        "composition": filled,
        "scoring_profile_key": campaign.scoring_profile_key,
        "quality_profile_key": campaign.quality_profile_key,
        "preferred": preferred,
        "gated_notices": gated_notices,
    }
