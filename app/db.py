from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, Session, create_engine, select

from app.engine.recipes import BUILTIN_RECIPES


class Recipe(SQLModel, table=True):
    id: str = Field(primary_key=True)
    category: str = ""
    type: str = ""
    logo: str = ""
    urlscan_query: str = ""
    publicwww_query: str = ""
    fingerprints_json: str = "[]"
    extractors_json: str = "{}"
    exclude_hosts_json: str = "[]"
    is_builtin: bool = False


class Job(SQLModel, table=True):
    id: str | None = Field(default=None, primary_key=True)
    recipe_id: str = ""
    source: str = "urlscan"
    filters_json: str = "{}"
    columns_json: str = "[]"
    status: str = "pending"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    totals_json: str = "{}"


class Lead(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_id: str = ""
    name: str = ""
    website: str = ""
    on_platform: str = "N"
    matched: str = ""
    email: str = ""
    emails_all: str = ""
    phone: str = ""
    phones_all: str = ""
    ids_json: str = "{}"
    address: str = ""
    country: str = ""
    socials_json: str = "{}"
    source_query: str = ""
    found_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "Not contacted"
    notes: str = ""


def init_db(url: str = "sqlite:///leadscraper.db"):
    connect_args = {"check_same_thread": False}
    engine = create_engine(url, connect_args=connect_args)
    SQLModel.metadata.create_all(engine)
    return engine


def _recipe_to_api(r: Recipe) -> dict:
    return {
        "id": r.id, "category": r.category, "type": r.type, "logo": r.logo,
        "urlscan_query": r.urlscan_query, "publicwww_query": r.publicwww_query,
        "verify_fingerprints": json.loads(r.fingerprints_json or "[]"),
        "id_extractors": json.loads(r.extractors_json or "{}"),
        "exclude_hosts": json.loads(r.exclude_hosts_json or "[]"),
        "is_builtin": r.is_builtin,
    }


def seed_builtins(session: Session) -> None:
    for br in BUILTIN_RECIPES:
        existing = session.get(Recipe, br.id)
        if existing:
            continue
        session.add(Recipe(
            id=br.id, category=br.category, type=br.type, logo=br.logo,
            urlscan_query=br.urlscan_query, publicwww_query=br.publicwww_query,
            fingerprints_json=json.dumps(br.verify_fingerprints),
            extractors_json=json.dumps(br.id_extractors),
            exclude_hosts_json=json.dumps(br.exclude_hosts),
            is_builtin=True,
        ))
    session.commit()


def all_recipes(session: Session) -> list[dict]:
    rows = session.exec(select(Recipe)).all()
    return [_recipe_to_api(r) for r in rows]
