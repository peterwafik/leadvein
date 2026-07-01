import pathlib
import re


def test_core_targeting_is_grep_clean():
    root = pathlib.Path("app/core")
    pat = re.compile(r"energy|utility|osm|overpass|shopify|gloriafood|campaign", re.I)
    hits = []
    for p in root.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if pat.search(line):
                hits.append(f"{p}:{i}: {line.strip()}")
    assert hits == [], "forbidden strings leaked into app/core:\n" + "\n".join(hits)


def test_predicates_registered_on_app_import():
    import app.leadvault  # noqa: F401  (import triggers registration)
    from app.core.targeting import registry
    from app.targeting.runtime import register_targeting_runtime
    register_targeting_runtime()  # re-register: idempotent; guards against other tests clearing registry
    assert "geo.country" in registry.all_keys()
    assert "web.has_signal" in registry.all_keys()
