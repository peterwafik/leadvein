"""Geofabrik per-region OSM extracts — the bulk volume source (spec §1).

Free, ODbL, no key, no rate limit. One streaming download per region, cached
under var/pbf with a freshness window. RUNBOOK HONESTY: Great Britain is
~1.5-2.0 GB and parsing takes tens of minutes; per-country extracts are the
unit — whole-planet is out of scope."""
from __future__ import annotations

import os
import time

import requests

from app.adapters.base import SourceMeta

BASE = "https://download.geofabrik.de"

REGIONS: dict[str, dict] = {
    "great-britain": {"path": "europe/great-britain", "country": "GB",
                       "label": "United Kingdom (Great Britain)"},
    "ireland-and-northern-ireland": {"path": "europe/ireland-and-northern-ireland",
                                     "country": "IE", "label": "Ireland + Northern Ireland"},
    "monaco": {"path": "europe/monaco", "country": "MC",
                "label": "Monaco (tiny - live test region)"},
    # England county/metro extracts — smaller units for staged pilot imports.
    "oxfordshire": {"path": "europe/united-kingdom/england/oxfordshire",
                     "country": "GB", "label": "England - Oxfordshire"},
    "cambridgeshire": {"path": "europe/united-kingdom/england/cambridgeshire",
                        "country": "GB", "label": "England - Cambridgeshire"},
    "norfolk": {"path": "europe/united-kingdom/england/norfolk",
                 "country": "GB", "label": "England - Norfolk"},
    "greater-manchester": {"path": "europe/united-kingdom/england/greater-manchester",
                            "country": "GB", "label": "England - Greater Manchester"},
    "west-midlands": {"path": "europe/united-kingdom/england/west-midlands",
                       "country": "GB", "label": "England - West Midlands"},
    "greater-london": {"path": "europe/united-kingdom/england/greater-london",
                        "country": "GB", "label": "England - Greater London (large)"},
}


def _default_get(url: str, dest: str) -> None:
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        tmp = dest + ".part"
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        os.replace(tmp, dest)


def download_extract(region_key: str, *, dest_dir: str = os.path.join("var", "pbf"),
                     http_get=None, max_age_days: int = 7) -> str:
    region = REGIONS[region_key]
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"{region_key}-latest.osm.pbf")
    if os.path.exists(dest):
        age_days = (time.time() - os.path.getmtime(dest)) / 86400
        if age_days < max_age_days:
            return dest
    url = f"{BASE}/{region['path']}-latest.osm.pbf"
    (http_get or _default_get)(url, dest)
    return dest


class _Geofabrik:
    # driven by the background bulk-import job, not the synchronous discover/normalize ingest
    bulk_only = True

    meta = SourceMeta(key="osm_geofabrik", name="OpenStreetMap (Geofabrik extract)",
                      type="open_data", url=BASE, license="ODbL", key_env="")

    def attribution(self) -> str:
        return "© OpenStreetMap contributors (ODbL) · extract by Geofabrik GmbH"

    def discover(self, query):          # bulk import drives this source
        raise NotImplementedError("bulk import only")

    def normalize(self, raw):
        raise NotImplementedError("bulk import only")


GEOFABRIK = _Geofabrik()
