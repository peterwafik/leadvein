from __future__ import annotations

from pydantic import BaseModel, Field

from app.engine.recipes import Recipe

DEFAULT_COLUMNS = [
    "name", "website", "on_platform", "matched", "email", "emails_all",
    "phone", "phones_all", "ids", "address", "country", "socials",
    "platform", "source_query", "status", "notes",
]


class RecipeCreate(BaseModel):
    category: str
    type: str
    urlscan_query: str = ""
    publicwww_query: str = ""
    verify_fingerprints: list[str] = Field(default_factory=list)
    id_extractors: dict[str, str] = Field(default_factory=dict)
    exclude_hosts: list[str] = Field(default_factory=list)


class TestRecipeRequest(BaseModel):
    urlscan_query: str = ""
    publicwww_query: str = ""
    verify_fingerprints: list[str] = Field(default_factory=list)
    id_extractors: dict[str, str] = Field(default_factory=dict)
    exclude_hosts: list[str] = Field(default_factory=list)
    source: str = "urlscan"


class JobCreate(BaseModel):
    recipe_id: str
    source: str = "urlscan"
    keyword: str = ""
    country: str = ""
    limit: int = 200
    delay: float = 1.0
    concurrency: int = 5
    only_confirmed: bool = True
    manual_hosts: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=lambda: list(DEFAULT_COLUMNS))


def engine_recipe_from_api(d: dict) -> Recipe:
    return Recipe(
        id=d.get("id", "custom"),
        category=d.get("category", ""),
        type=d.get("type", ""),
        urlscan_query=d.get("urlscan_query", ""),
        publicwww_query=d.get("publicwww_query", ""),
        verify_fingerprints=list(d.get("verify_fingerprints", [])),
        id_extractors=dict(d.get("id_extractors", {})),
        exclude_hosts=list(d.get("exclude_hosts", [])),
        is_builtin=bool(d.get("is_builtin", False)),
    )
