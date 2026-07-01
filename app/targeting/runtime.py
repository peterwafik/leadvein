from __future__ import annotations
from app.core.targeting import registry
from app.targeting.predicates import geo, quality, category, contactability, webpresence


def register_targeting_runtime() -> None:
    for p in (geo.GEO_COUNTRY, geo.GEO_REGION, geo.GEO_CITY,
              quality.MIN_SCORE, quality.VERIFIED_WITHIN, quality.SOURCE_TYPE,
              category.CATEGORY_ANY,
              contactability.HAS_PHONE, contactability.HAS_ROLE_EMAIL,
              contactability.HAS_BUSINESS_CONTACT,
              webpresence.HAS_SIGNAL, webpresence.IS_ENRICHED):
        registry.register(p)
