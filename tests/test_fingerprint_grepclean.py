"""Grep gate: vendor/fingerprint strings must never appear in app/core.

This mirrors test_campaign_grepclean.py.  All catalog strings (gloriafood,
shopify, fbgcdn, urlscan, publicwww …) must live in app/fingerprints/, never
bleed into the generic core package.
"""
import pathlib
import re


def test_core_is_fingerprint_grep_clean():
    """Assert that vendor/fingerprint strings do not leak into app/core/**/*.py."""
    root = pathlib.Path("app/core")
    pat = re.compile(
        r"gloriafood|chownow|shopify|fbgcdn|ewm2|data-glf|wappalyzer|urlscan|publicwww",
        re.I,
    )
    hits = []
    for p in root.rglob("*.py"):
        for i, line in enumerate(
            p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            if pat.search(line):
                hits.append(f"{p}:{i}: {line.strip()}")
    assert hits == [], (
        "Vendor/fingerprint strings leaked into app/core:\n" + "\n".join(hits)
    )
