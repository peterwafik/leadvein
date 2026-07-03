from __future__ import annotations

import os
import re
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


# ---------------------------------------------------------------------------
# capability-marker + sync-ingest exclusion tests
# ---------------------------------------------------------------------------

def test_geofabrik_not_in_sync_ingest_keys():
    """osm_geofabrik (bulk_only) must be excluded; osm_overpass (open_data, sync)
    must remain — guards against the type-based-overreach mistake."""
    import app.adapters.providers as prov
    prov.register_providers()
    # osm_overpass is registered via seed.register_runtime, not register_providers
    from app.seed import register_runtime
    register_runtime()

    from app.web.routes_admin import _generic_ingest_keys
    keys = _generic_ingest_keys()

    assert "osm_geofabrik" not in keys, (
        f"osm_geofabrik (bulk_only) must NOT appear in sync-ingest keys; got {keys}"
    )
    assert "osm_overpass" in keys, (
        f"osm_overpass (open_data, sync) MUST appear in sync-ingest keys; got {keys}"
    )


def test_sync_ingest_rejects_bulk_only_key():
    """POST /admin/ingest with adapter_key=osm_geofabrik must redirect/error,
    never 500 — the existing not-in-keys guard in routes_admin.py handles it."""
    from fastapi.testclient import TestClient
    import app.leadvault as lv

    c = TestClient(lv.app)
    login_page = c.get("/login").text
    m = re.search(r'name="csrf_token" value="([^"]+)"', login_page)
    token = m.group(1) if m else ""
    c.post("/login", data={"email": "admin@leadvault.local",
                           "password": "admin12345", "csrf_token": token})

    r = c.post("/admin/ingest", data={
        "adapter_key": "osm_geofabrik",
        "city": "London",
        "categories": "",
        "scoring_profile_key": "utility_energy",
        "csrf_token": token,
    })
    # Must NOT 500 — the not-in-keys guard returns a 200 error page
    assert r.status_code != 500, (
        f"POST /admin/ingest with osm_geofabrik must not 500; got {r.status_code}"
    )
    # Must not expose NotImplementedError traceback
    assert "NotImplementedError" not in r.text, (
        "Response must not expose NotImplementedError from Geofabrik discover()"
    )
