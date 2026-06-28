import importlib


def test_core_packages_import():
    for mod in ["app.core", "app.adapters", "app.enrich", "app.scoring",
                "app.scoring.profiles", "app.ingestion"]:
        assert importlib.import_module(mod) is not None
