"""Import a GeoNames snapshot into the geo_ref table (or regenerate the committed fixture).

GeoNames data: https://download.geonames.org/export/dump/ — CC BY 4.0.
This script is the ONLY place geo reference data crosses the network. Seeds never do.

Usage:
  python scripts/import_geonames.py                 # full import into leadvault.db
  python scripts/import_geonames.py --db sqlite:///leadvault.db
  python scripts/import_geonames.py --write-fixture app/geo/data/geo_fixture.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = "https://download.geonames.org/export/dump/"
FIXTURE_COUNTRIES = None  # None = all
FIXTURE_CITY_COUNTRIES = {"GB", "US", "DE", "FR", "IE"}   # fixture keeps cities small


def _fetch(name: str) -> str:
    with urllib.request.urlopen(BASE + name, timeout=120) as r:
        data = r.read()
    if name.endswith(".zip"):
        zf = zipfile.ZipFile(io.BytesIO(data))
        inner = name.replace(".zip", ".txt")
        return zf.read(inner).decode("utf-8")
    return data.decode("utf-8")


def _rows():
    """Yield dict rows (same schema as the fixture CSV) for the full snapshot."""
    countries = {}
    for line in _fetch("countryInfo.txt").splitlines():
        if not line or line.startswith("#"):
            continue
        p = line.split("\t")
        countries[p[0]] = {"name": p[4], "population": int(p[7] or 0),
                           "geoname_id": int(p[16] or 0)}
    for code, c in sorted(countries.items()):
        yield {"kind": "country", "geoname_id": c["geoname_id"], "country_code": code,
               "country_name": c["name"], "admin1_name": "", "admin2_name": "",
               "name": c["name"], "ascii_name": c["name"], "population": c["population"]}

    admin1 = {}   # "GB.ENG" -> "England"
    for line in _fetch("admin1CodesASCII.txt").splitlines():
        p = line.split("\t")
        if len(p) >= 2:
            admin1[p[0]] = p[1]
    admin2 = {}   # "GB.ENG.K2" -> "Oxfordshire"
    for line in _fetch("admin2Codes.txt").splitlines():
        p = line.split("\t")
        if len(p) >= 2:
            admin2[p[0]] = p[1]

    for key, name in sorted(admin1.items()):
        cc = key.split(".")[0]
        if cc not in countries:
            continue
        yield {"kind": "region", "geoname_id": 0, "country_code": cc,
               "country_name": countries[cc]["name"], "admin1_name": name,
               "admin2_name": "", "name": name, "ascii_name": name, "population": 0}
    for key, name in sorted(admin2.items()):
        cc = key.split(".")[0]
        if cc not in countries:
            continue
        a1 = admin1.get(".".join(key.split(".")[:2]), "")
        yield {"kind": "region", "geoname_id": 0, "country_code": cc,
               "country_name": countries[cc]["name"], "admin1_name": a1,
               "admin2_name": name, "name": name, "ascii_name": name, "population": 0}

    for line in _fetch("cities1000.zip").splitlines():
        p = line.split("\t")
        if len(p) < 15:
            continue
        cc = p[8]
        if cc not in countries:
            continue
        a1 = admin1.get(f"{cc}.{p[10]}", "")
        a2 = admin2.get(f"{cc}.{p[10]}.{p[11]}", "")
        yield {"kind": "city", "geoname_id": int(p[0]), "country_code": cc,
               "country_name": countries[cc]["name"], "admin1_name": a1,
               "admin2_name": a2, "name": p[1], "ascii_name": p[2],
               "population": int(p[14] or 0)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.getenv("LEADVAULT_DB", "sqlite:///leadvault.db"))
    ap.add_argument("--write-fixture", default="")
    args = ap.parse_args()

    if args.write_fixture:
        fields = ["kind", "geoname_id", "country_code", "country_name",
                  "admin1_name", "admin2_name", "name", "ascii_name", "population"]
        keep_cities = {"Oxford", "Banbury", "Bicester", "Cambridge", "Peterborough",
                       "Leeds", "London", "Norwich", "Birmingham", "Manchester",
                       "Glasgow", "Edinburgh", "Cardiff", "New York", "San Francisco",
                       "Boston", "Berlin", "Hamburg", "Paris", "Dublin"}
        with open(args.write_fixture, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in _rows():
                if r["kind"] == "country":
                    w.writerow(r)
                elif r["kind"] == "region" and r["country_code"] == "GB":
                    w.writerow(r)
                elif (r["kind"] == "city" and r["country_code"] in FIXTURE_CITY_COUNTRIES
                      and r["name"] in keep_cities):
                    w.writerow(r)
        print(f"fixture written: {args.write_fixture}")
        return

    from sqlmodel import Session, create_engine, select
    from app.geo.ref import GeoRef
    engine = create_engine(args.db)
    GeoRef.metadata.create_all(engine, tables=[GeoRef.__table__])
    with Session(engine) as s:
        # Full import replaces reference rows (safe: pure reference data)
        for row in s.exec(select(GeoRef)).all():
            s.delete(row)
        s.commit()
        n = 0
        for r in _rows():
            s.add(GeoRef(**{k: r[k] for k in r}))
            n += 1
            if n % 5000 == 0:
                s.commit()
        s.commit()
    print(f"imported {n} geo_ref rows")


if __name__ == "__main__":
    main()
