import pathlib
import re


def test_core_is_campaign_grep_clean():
    """Assert that no campaign/vertical/financial strings leak into app/core.

    app/core must remain independent of campaign concepts, named verticals,
    and financial-distress vocabulary (MCA, lender, amount_owed, restructuring).
    Mirrors test_composer_grepclean.py (INV-Q5 variant for campaigns).
    """
    root = pathlib.Path("app/core")
    pat = re.compile(
        r"campaign|utilit|restructur|mca|lender|amount_owed|vertical",
        re.I,
    )
    hits = []
    for p in root.rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if pat.search(line):
                hits.append(f"{p}:{i}: {line.strip()}")
    assert hits == [], "campaign/vertical strings leaked into app/core:\n" + "\n".join(hits)
