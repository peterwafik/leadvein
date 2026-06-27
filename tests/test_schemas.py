from app.schemas import engine_recipe_from_api, DEFAULT_COLUMNS, JobCreate


def test_engine_recipe_from_api_roundtrip():
    d = {
        "id": "calendly", "category": "Booking / Scheduling", "type": "Calendly",
        "urlscan_query": "domain:assets.calendly.com", "publicwww_query": "",
        "verify_fingerprints": ["assets.calendly.com"], "id_extractors": {},
        "exclude_hosts": ["calendly.com"],
    }
    r = engine_recipe_from_api(d)
    assert r.type == "Calendly"
    assert r.verify_fingerprints == ["assets.calendly.com"]


def test_default_columns_present():
    for c in ["name", "website", "on_platform", "email", "phone", "status"]:
        assert c in DEFAULT_COLUMNS


def test_jobcreate_defaults():
    jc = JobCreate(recipe_id="gloriafood")
    assert jc.source == "urlscan"
    assert jc.limit == 200
    assert jc.only_confirmed is True
    assert jc.manual_hosts == []
