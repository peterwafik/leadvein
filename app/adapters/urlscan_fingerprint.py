from __future__ import annotations

from typing import Iterable

from app.adapters.base import SourceMeta, AdapterQuery, NormalizedLead
from app.engine.recipes import get_builtin
from app.engine.discover import discover as engine_discover
from app.engine.enrich import analyse, fetch as engine_fetch, norm_url


class UrlscanFingerprintAdapter:
    meta = SourceMeta(key="urlscan_fingerprint", name="urlscan.io fingerprint",
                      type="tech_detection", url="https://urlscan.io",
                      license="urlscan.io ToS (public scan index)")

    def discover(self, query: AdapterQuery, *, hosts_fn=None) -> Iterable[dict]:
        recipe_id = query.extra.get("recipe_id", "")
        hosts = query.extra.get("hosts")
        if hosts is None:
            recipe = get_builtin(recipe_id)
            fn = hosts_fn or (lambda r: engine_discover(
                r, source="urlscan", limit=query.limit))
            hosts = fn(recipe) if recipe else []
        return [{"host": h, "recipe_id": recipe_id} for h in hosts]

    def normalize(self, raw: dict, *, fetch_fn=engine_fetch) -> NormalizedLead | None:
        host = raw.get("host")
        if not host:
            return None
        recipe = get_builtin(raw.get("recipe_id", ""))
        url = norm_url(host)
        final_url, html = fetch_fn(url)
        if not html or recipe is None:
            return None
        lead = analyse(recipe, final_url or url, html)
        return NormalizedLead(
            business_name=lead.name,
            category_keys=[],
            address={"country": lead.country},
            phone=lead.phones[0] if lead.phones else "",
            public_email=lead.emails[0] if lead.emails else "",
            website_url=lead.website,
            attributes={"on_platform": lead.on_platform,
                        "matched_fingerprint": lead.matched,
                        "detected_platform": recipe.type},
            source_key=self.meta.key, source_url=lead.website,
            source_license=self.meta.license, raw_ref=host)

    def attribution(self) -> str:
        return "Technology detected from public page source via urlscan.io index"
