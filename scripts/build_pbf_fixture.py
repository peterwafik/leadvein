"""One-time fixture builder: .osm XML -> .osm.pbf via pyosmium. Run manually;
the committed .pbf is what tests consume (no osmium tooling needed at test time).

pyosmium 4.0.2 API notes:
- osmium.FileProcessor exists and supports __iter__
- osmium.SimpleWriter exists with add_node / add_way / add_relation
- obj.is_node() / obj.is_way() / obj.is_relation() available on all OSM objects
- overwrite=True passed to SimpleWriter so re-runs don't need manual removal
"""
from __future__ import annotations

import os
import sys

import osmium

SRC = os.path.join("tests", "fixtures", "bulk_fixture.osm")
DST = os.path.join("tests", "fixtures", "bulk_fixture.osm.pbf")


def main() -> None:
    writer = osmium.SimpleWriter(DST, overwrite=True)
    try:
        for obj in osmium.FileProcessor(SRC):
            if obj.is_node():
                writer.add_node(obj)
            elif obj.is_way():
                writer.add_way(obj)
            elif obj.is_relation():
                writer.add_relation(obj)
    finally:
        writer.close()
    size = os.path.getsize(DST)
    print(f"wrote {DST} ({size} bytes)")


if __name__ == "__main__":
    sys.exit(main())
