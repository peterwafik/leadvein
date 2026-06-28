from __future__ import annotations

import json

from sqlmodel import Session, select

from app.core.db import LeadSource
from app.core.taxonomy import seed_taxonomy, add_mapping, categories_for_external
from app.adapters import registry as adapter_registry
from app.adapters.osm import OsmOverpassAdapter, CATEGORY_TO_OSM
from app.adapters.urlscan_fingerprint import UrlscanFingerprintAdapter
from app.scoring.profiles import registry as profile_registry
from app.scoring.profiles.utility_energy import UtilityEnergyProfile


def _ensure_source(session: Session, meta) -> None:
    if not session.exec(select(LeadSource).where(LeadSource.key == meta.key)).first():
        session.add(LeadSource(key=meta.key, name=meta.name, type=meta.type,
                               url=meta.url, license=meta.license,
                               terms_status=meta.terms_status,
                               regions_json=json.dumps(meta.regions)))
        session.commit()


def register_runtime() -> None:
    """Register adapters + scoring profiles (idempotent, in-memory)."""
    adapter_registry.register(OsmOverpassAdapter())
    adapter_registry.register(UrlscanFingerprintAdapter())
    profile_registry.register(UtilityEnergyProfile())


def seed_all(session: Session) -> None:
    register_runtime()
    seed_taxonomy(session)
    for meta in (OsmOverpassAdapter().meta, UrlscanFingerprintAdapter().meta):
        _ensure_source(session, meta)
    # seed OSM category mappings so the OSM adapter's tags resolve to taxonomy keys
    for cat_key, osm_tag in CATEGORY_TO_OSM.items():
        if not categories_for_external(session, "osm_overpass", osm_tag):
            add_mapping(session, "osm_overpass", osm_tag, cat_key)
