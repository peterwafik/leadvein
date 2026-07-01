import pathlib, re


def test_core_is_quality_and_provider_clean():   # INV-Q5
    root = pathlib.Path("app/core")
    pat = re.compile(r"quality|energy|utility|osm|overpass|campaign|provider|mca|lender", re.I)
    hits = []
    for p in root.rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if pat.search(line):
                hits.append(f"{p}:{i}: {line.strip()}")
    assert hits == [], "quality/provider strings leaked into app/core:\n" + "\n".join(hits)
