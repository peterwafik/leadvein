from __future__ import annotations

from sqlmodel import Session

from app.core.sources import ensure_source
from app.core.taxonomy import seed_taxonomy
from app.adapters import registry as adapter_registry
from app.adapters.osm import OsmOverpassAdapter
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
    # NOTE: each adapter owns its source->taxonomy mapping in slice one; admin-editable
    # CategoryMapping wiring is a Plan-2 follow-up.
