from __future__ import annotations

from sqlmodel import Session

from app.core.sources import ensure_source
from app.core.taxonomy import seed_taxonomy, add_mapping, categories_for_external
from app.adapters import registry as adapter_registry
from app.adapters.osm import OsmOverpassAdapter, CATEGORY_TO_OSM
from app.adapters.urlscan_fingerprint import UrlscanFingerprintAdapter
from app.scoring.profiles import registry as profile_registry
from app.scoring.profiles.utility_energy import UtilityEnergyProfile


def register_runtime() -> None:
    """Register adapters + scoring profiles (idempotent, in-memory)."""
    adapter_registry.register(OsmOverpassAdapter())
    adapter_registry.register(UrlscanFingerprintAdapter())
    profile_registry.register(UtilityEnergyProfile())


def seed_all(session: Session) -> None:
    osm = OsmOverpassAdapter()
    urlscan = UrlscanFingerprintAdapter()
    adapter_registry.register(osm)
    adapter_registry.register(urlscan)
    profile_registry.register(UtilityEnergyProfile())
    seed_taxonomy(session)
    for adapter in (osm, urlscan):
        ensure_source(session, adapter.meta)
    # seed OSM category mappings so the OSM adapter's tags resolve to taxonomy keys
    for cat_key, osm_tag in CATEGORY_TO_OSM.items():
        if not categories_for_external(session, "osm_overpass", osm_tag):
            add_mapping(session, "osm_overpass", osm_tag, cat_key)
