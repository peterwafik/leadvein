import pathlib, re


def test_core_is_composer_grep_clean():   # INV-Q5 (composer variant)
    """Assert that no composer/provider-layer strings leak into app/core.

    app/core must remain independent of any specific data-source vocabulary
    (quality profiles, energy/utility domains, OSM/Overpass specifics,
    campaign concepts, named providers, MCA/lender verticals).
    """
    root = pathlib.Path("app/core")
    pat = re.compile(r"quality|energy|utility|osm|overpass|campaign|provider|mca|lender", re.I)
    hits = []
    for p in root.rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if pat.search(line):
                hits.append(f"{p}:{i}: {line.strip()}")
    assert hits == [], "composer/provider strings leaked into app/core:\n" + "\n".join(hits)
