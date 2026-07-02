"""INV grep-clean gate for app/core — provider-name variant.

Asserts that no provider/data-vendor vocabulary leaks into app/core.  The core
must remain agnostic: it knows nothing about Hunter, Apollo, Companies House,
Foursquare, People Data Labs, LinkedIn, Google Places, Yelp, TCPA, or DNC.
Those names belong exclusively in app/adapters or app/compliance, never in the
shared core that buyers and all other layers depend on.

If this test finds a real hit, the string must be RELOCATED out of app/core —
do NOT weaken this test to suppress a genuine violation.
"""
import pathlib
import re


def test_core_is_enrichment_provider_grep_clean():
    """Assert that no provider-layer strings from the enrichment pipeline leak
    into app/core.

    Pattern mirrors the brief's grep gate:
        hunter|apollo|companies|foursquare|people.?data|linkedin
        |google.?places|yelp|tcpa|dnc
    """
    root = pathlib.Path("app/core")
    pat = re.compile(
        r"hunter|apollo|companies|foursquare|people.?data|linkedin"
        r"|google.?places|yelp|tcpa|dnc",
        re.I,
    )
    hits: list[str] = []
    for p in root.rglob("*.py"):
        for i, line in enumerate(
            p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            if pat.search(line):
                hits.append(f"{p}:{i}: {line.strip()}")

    assert hits == [], (
        "Provider/vendor strings leaked into app/core — relocate them, "
        "do NOT weaken this test:\n" + "\n".join(hits)
    )
