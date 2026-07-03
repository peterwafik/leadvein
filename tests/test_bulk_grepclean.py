"""INV: app/core stays generic — bulk vendor strings must not leak in."""
from __future__ import annotations

import pathlib
import re

CORE = pathlib.Path(__file__).resolve().parents[1] / "app" / "core"
PATTERN = re.compile(r"geofabrik|osmium|pbf", re.IGNORECASE)


def test_core_free_of_bulk_vendor_strings():
    offenders = []
    for py in CORE.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        if PATTERN.search(text):
            offenders.append(str(py))
    assert not offenders, f"bulk vendor strings leaked into core: {offenders}"
