"""Static geographic reference (GeoNames-derived snapshot; CC BY 4.0 attribution
in README + find page). Seeding is CSV-only — NO network in any seed path.
Full snapshot import: scripts/import_geonames.py (manual, network)."""
from __future__ import annotations

import csv
import os

from sqlalchemy import func, or_
from sqlmodel import Field, SQLModel, Session, select

_FIXTURE = os.path.join(os.path.dirname(__file__), "data", "geo_fixture.csv")


class GeoRef(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    geoname_id: int = Field(default=0, index=True)
    country_code: str = Field(default="", index=True)   # ISO-2
    country_name: str = ""
    admin1_name: str = Field(default="", index=True)
    admin2_name: str = Field(default="", index=True)
    name: str = Field(default="", index=True)
    ascii_name: str = Field(default="", index=True)
    kind: str = Field(default="city", index=True)       # country | region | city
    population: int = 0


def seed_geo_fixture(session: Session) -> int:
    """Load the committed fixture if the table is empty. Idempotent, offline."""
    if session.exec(select(GeoRef.id).limit(1)).first() is not None:
        return 0
    n = 0
    with open(_FIXTURE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            session.add(GeoRef(
                geoname_id=int(row["geoname_id"] or 0),
                country_code=row["country_code"].upper(),
                country_name=row["country_name"],
                admin1_name=row["admin1_name"],
                admin2_name=row["admin2_name"],
                name=row["name"],
                ascii_name=row["ascii_name"] or row["name"],
                kind=row["kind"],
                population=int(row["population"] or 0),
            ))
            n += 1
    session.commit()
    return n


def list_countries(session: Session) -> list[GeoRef]:
    return list(session.exec(
        select(GeoRef).where(GeoRef.kind == "country")
        .order_by(GeoRef.country_name)).all())


def search_areas(session: Session, country: str, q: str, limit: int = 60) -> list[GeoRef]:
    stmt = select(GeoRef).where(
        GeoRef.country_code == (country or "").upper(),
        GeoRef.kind.in_(("region", "city")))
    q = (q or "").strip().lower()
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(func.lower(GeoRef.ascii_name).like(like),
                              func.lower(GeoRef.name).like(like)))
    stmt = stmt.order_by(GeoRef.population.desc(), GeoRef.name).limit(limit)
    return list(session.exec(stmt).all())
