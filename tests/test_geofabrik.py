from __future__ import annotations

import os
import time

from app.adapters.geofabrik import REGIONS, download_extract, GEOFABRIK


def test_regions_config_shape():
    assert "great-britain" in REGIONS and "monaco" in REGIONS
    for r in REGIONS.values():
        assert set(r) >= {"path", "country", "label"}


def test_download_uses_cache_when_fresh(tmp_path):
    calls = []
    def fake_get(url, dest):
        calls.append(url)
        with open(dest, "wb") as f:
            f.write(b"pbf-bytes")
    p1 = download_extract("monaco", dest_dir=str(tmp_path), http_get=fake_get)
    p2 = download_extract("monaco", dest_dir=str(tmp_path), http_get=fake_get)
    assert p1 == p2 and os.path.exists(p1)
    assert len(calls) == 1                      # second call hit the cache
    assert "europe/monaco-latest.osm.pbf" in calls[0]


def test_stale_cache_redownloads(tmp_path):
    calls = []
    def fake_get(url, dest):
        calls.append(url)
        with open(dest, "wb") as f:
            f.write(b"pbf")
    p = download_extract("monaco", dest_dir=str(tmp_path), http_get=fake_get)
    old = time.time() - 8 * 86400
    os.utime(p, (old, old))
    download_extract("monaco", dest_dir=str(tmp_path), http_get=fake_get)
    assert len(calls) == 2


def test_attribution_and_meta():
    assert GEOFABRIK.meta.key == "osm_geofabrik"
    assert GEOFABRIK.meta.license == "ODbL"
    assert "OpenStreetMap contributors" in GEOFABRIK.attribution()
    assert "Geofabrik" in GEOFABRIK.attribution()
