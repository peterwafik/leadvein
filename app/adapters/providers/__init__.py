"""Provider adapter package.

Call ``register_providers()`` once at startup to surface Companies House and
Hunter.io in the admin "Connected sources" table.  Both are registered as
DISABLED until their respective env keys are set; ``run_enrichment`` takes an
explicit adapters list and is unaffected by registry registration.
"""
from __future__ import annotations


def register_providers() -> None:
    """Register provider adapters with the global adapter registry.

    Safe to call multiple times — re-registration overwrites the same key.
    Adapters report ``enabled=False`` until their env key is set:
      - LEADVAULT_COMPANIES_HOUSE_KEY  (CompaniesHouseAdapter)
      - LEADVAULT_HUNTER_KEY           (HunterAdapter)
    """
    from app.adapters import registry
    from app.adapters.providers.companies_house import CompaniesHouseAdapter
    from app.adapters.providers.hunter import HunterAdapter
    from app.adapters.providers.fingerprint_discovery import FingerprintDiscoveryAdapter
    from app.adapters.geofabrik import GEOFABRIK

    registry.register(CompaniesHouseAdapter())
    registry.register(HunterAdapter())
    registry.register(FingerprintDiscoveryAdapter())
    registry.register(GEOFABRIK)
