"""FingerprintDiscoveryAdapter — PRIMARY source adapter.

Runs enabled fingerprint recipes (from the DB catalog), confirms the
technology fingerprint on each business's OWN homepage, and records
multi-signal match strength.

INV-12: A page that merely LINKS to the vendor but does not embed the
technology (i.e. zero verify_fingerprints matched in the HTML) is
rejected — normalize() returns None.
"""
from __future__ import annotations

from typing import Iterable

from app.adapters.base import SourceMeta, AdapterQuery, NormalizedLead
from app.engine.discover import discover as engine_discover
from app.engine.enrich import analyse, fetch as engine_fetch, norm_url
from app.fingerprints.library import list_recipes, get_recipe, to_engine_recipe

# FIX 5: clean base license stored on SourceMeta; per-lead license includes
# the recipe name via _LICENSE_TMPL.format(tech=...) in normalize().
_BASE_LICENSE = "Detected from public page source via urlscan.io index"
_LICENSE_TMPL = _BASE_LICENSE + " (recipe: {tech})"


class FingerprintDiscoveryAdapter:
    meta = SourceMeta(
        key="fingerprint",
        name="Technology fingerprint",
        type="fingerprint_discovery",
        url="https://urlscan.io",
        # FIX 5: clean base string — no template placeholder stored on the source meta
        license=_BASE_LICENSE,
        terms_status="permitted",
        regions=["*"],
        key_env="",          # urlscan free default; URLSCAN_KEY optional
        rate_limit={"per": 100, "seconds": 60},
    )

    # ------------------------------------------------------------------
    # LeadSourceAdapter protocol
    # ------------------------------------------------------------------

    def discover(
        self,
        query: AdapterQuery,
        *,
        session,
        discover_fn=None,
    ) -> Iterable[dict]:
        """Yield {host, recipe_key} dicts for each discovered host.

        *discover_fn* is injected in tests; defaults to the real urlscan
        engine (``engine_discover(recipe, source="urlscan", limit=query.limit)``).
        Disabled / greyed recipes are silently skipped.
        """
        recipe_key = query.extra.get("recipe_key")
        category = query.extra.get("category")

        if recipe_key:
            row = get_recipe(session, recipe_key)
            rows = [row] if (row is not None and row.enabled) else []
        else:
            rows = list_recipes(
                session,
                enabled=True,
                category=category if category else None,
            )

        def _default_fn(recipe):
            return engine_discover(recipe, source="urlscan", limit=query.limit)

        fn = discover_fn or _default_fn

        for row in rows:
            recipe = to_engine_recipe(row)
            hosts = fn(recipe)
            for h in hosts:
                yield {"host": h, "recipe_key": row.recipe_key}

    def normalize(
        self,
        raw: dict,
        *,
        session,
        fetch_fn=None,
    ) -> NormalizedLead | None:
        """Fetch the host's OWN homepage and confirm fingerprint presence.

        INV-12: returns None when zero verify_fingerprints are found in the
        page HTML — a page that merely links to the vendor is not a match.

        FIX 4: belt-and-suspenders vendor exclusion — if the host matches any
        recipe.exclude_hosts token, returns None immediately (never enrich the
        vendor's own domain), independent of what discover() already filtered.
        """
        host = raw.get("host")
        recipe_key = raw.get("recipe_key")
        if not host or not recipe_key:
            return None

        row = get_recipe(session, recipe_key)
        if row is None or not row.enabled:
            return None

        recipe = to_engine_recipe(row)

        # FIX 4: belt-and-suspenders vendor exclusion (mirrors normalize_hosts in
        # engine/discover.py).  Guard against the vendor's own domain slipping
        # through discover() (e.g. after a discover_fn override in tests or after
        # manual queue injection).
        host_lower = host.lower().strip()
        excl = [e.lower() for e in recipe.exclude_hosts]
        if any(tok in host_lower for tok in excl):
            return None  # vendor's own domain — never enrich

        url = norm_url(host)
        _fetch = fetch_fn or engine_fetch
        final_url, html = _fetch(url)
        if not html:
            return None

        # OWN-HOMEPAGE CONFIRMATION (INV-12): count matched verify_fingerprints.
        low_html = html.lower()
        matched_all = [
            fp for fp in recipe.verify_fingerprints
            if fp.lower() in low_html
        ]
        if not matched_all:
            return None   # zero fingerprint signals on this page — skip

        match_strength = len(matched_all)

        # Full enrichment: name, emails, phones, ids (id_extractors), country.
        lead = analyse(recipe, final_url or url, html)

        attrs: dict = {
            "matched": matched_all,
            "match_strength": match_strength,
            "recipe_key": recipe_key,
            "tech_type": recipe.type,
            "on_platform": lead.on_platform,
            **lead.ids,   # e.g. ruid, cuid for gloriafood
        }

        # FIX 5: per-lead license includes the recipe name (not stored on meta)
        license_str = _LICENSE_TMPL.format(tech=recipe.type)

        return NormalizedLead(
            business_name=lead.name,
            category_keys=[],
            address={"country": lead.country},
            phone=lead.phones[0] if lead.phones else "",
            public_email=lead.emails[0] if lead.emails else "",
            website_url=lead.website,
            attributes=attrs,
            source_key="fingerprint",
            source_url=lead.website,
            source_license=license_str,
            raw_ref=host,
        )

    def attribution(self) -> str:
        return (
            "Technology fingerprints detected from public page source via "
            "urlscan.io index. Recipe-driven multi-signal detection with "
            "own-homepage confirmation (INV-12)."
        )
