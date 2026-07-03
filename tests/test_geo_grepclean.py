"""INV: app/core stays generic — geo reference vendor strings must not leak in."""
from __future__ import annotations

import pathlib
import re

CORE = pathlib.Path(__file__).resolve().parents[1] / "app" / "core"
PATTERN = re.compile(r"geonames", re.IGNORECASE)


def test_core_free_of_geo_vendor_strings():
    offenders = []
    for py in CORE.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        if PATTERN.search(text):
            offenders.append(str(py))
    assert not offenders, f"geo vendor strings leaked into core: {offenders}"


def test_core_does_not_import_geo_package():
    offenders = []
    for py in CORE.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"from app\.geo|import app\.geo", text):
            offenders.append(str(py))
    assert not offenders, f"core must not depend on app.geo: {offenders}"
