"""Deterministic plain-language rendering of a COMPILED composition.

The sentence is generated from the composition that will actually run (plus the
quality profiles that will actually gate), never from raw user input — so the
words cannot drift from the behavior. Order of clauses is fixed."""
from __future__ import annotations

_QUALITY_LABEL = {50: "Good (50+)", 70: "Strong (70+)", 85: "Best (85+)"}

_CHANNEL_TEXT = {"contactability.has_phone": "a phone number",
                 "contactability.has_role_email": "a business email",
                 "contactability.has_business_contact": "a phone or business email"}

_PROFILE_TEXT = {"phone_validated": "a validated phone number",
                 "email_validated": "a validated email address",
                 "contact_validated": "a validated phone or email",
                 "utilities": "a validated phone number",
                 "baseline": ""}


def _join_or(items: list[str]) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " or " + items[-1]


def _country_name(session, code: str) -> str:
    from app.geo.ref import GeoRef
    from sqlmodel import select
    row = session.exec(select(GeoRef).where(
        GeoRef.kind == "country", GeoRef.country_code == code.upper())).first()
    return row.country_name if row else code


def _tech_label(session, recipe_key: str) -> str:
    from app.fingerprints.library import get_recipe
    r = get_recipe(session, recipe_key)
    return r.tech_type if r else recipe_key


def _flat_nodes(composition: dict) -> list[dict]:
    out: list[dict] = []
    def walk(node):
        if "op" in node:
            for n in node.get("nodes", []):
                walk(n)
        else:
            out.append(node)
    walk(composition or {})
    return out


def render_sentence(session, composition: dict, quality_profile_keys=()) -> str:
    nodes = _flat_nodes(composition)
    who, tech, where, extras = [], [], [], []
    contact = ""
    quality = ""
    freshness = ""
    advanced = 0

    for node in nodes:
        pred = node.get("predicate", "")
        params = node.get("params", {}) or {}
        if node.get("negate"):
            advanced += 1
            continue
        if pred == "category.any":
            who += [c.replace("_", " ") for c in params.get("in", [])]
        elif pred == "web.runs_tech":
            tech += [_tech_label(session, k) for k in params.get("recipe_in", [])]
            if int(params.get("min_strength") or 1) > 1:
                extras.append(f"with at least {params['min_strength']} confirmed signals")
        elif pred in ("geo.city_any", "geo.region_any"):
            where += list(params.get("in", []))
        elif pred in ("geo.city", "geo.region"):
            if params.get("value"):
                where.append(params["value"])
        elif pred == "geo.country_any":
            where += [f"across {_country_name(session, c)}" for c in params.get("in", [])]
        elif pred == "geo.country":
            if params.get("value"):
                where.append(f"across {_country_name(session, params['value'])}")
        elif pred in _CHANNEL_TEXT:
            contact = _CHANNEL_TEXT[pred]
        elif pred == "quality.min_score":
            quality = _QUALITY_LABEL.get(int(params.get("min") or 0),
                                         f"{params.get('min')}+")
        elif pred == "freshness.verified_within":
            freshness = f"verified within the last {params.get('days')} days"
        else:
            advanced += 1

    for key in quality_profile_keys or ():
        t = _PROFILE_TEXT.get(key)
        if t:
            contact = t          # gate text (validated …) supersedes presence text

    subject = _join_or(sorted(set(who))) + " businesses" if who else "businesses"
    parts = [f"We'll find {subject}" if who else "We'll find all available business leads"
             if not (tech or where or contact or quality or freshness or advanced)
             else f"We'll find {subject}"]
    if tech:
        parts.append(f"that run {_join_or(sorted(set(tech)))} on their website")
    if extras:
        parts.append(_join_or(extras))
    if where:
        plain = [w for w in where if not w.startswith("across ")]
        scoped = [w for w in where if w.startswith("across ")]
        loc = _join_or(plain)
        if loc:
            parts.append(f"in {loc}")
        if scoped:
            parts.append(("or " if loc else "") + _join_or(scoped))
    if contact:
        parts.append(f"with {contact}")
    if quality:
        parts.append(f"at quality {quality}")
    if freshness:
        parts.append(freshness)
    if advanced:
        parts.append(f"matching {advanced} advanced condition{'s' if advanced != 1 else ''}")
    return ", ".join([parts[0]] + parts[1:]) + "."
