"""FingerprintRecipe ORM model.

Lives in app/fingerprints (NOT app/core) so that vendor-specific catalog data
never bleeds into the generic core package (grep gate: test_fingerprint_grepclean.py).
"""
from __future__ import annotations

from sqlmodel import Field, SQLModel


class FingerprintRecipe(SQLModel, table=True):
    """Persistent catalog entry for a tech-fingerprint detection recipe.

    JSON fields (verify_fingerprints_json, id_extractors_json, exclude_hosts_json)
    are stored as raw JSON strings; callers use json.loads / json.dumps.

    confidence: "high" | "medium" | "low"
    source:     "custom" for catalog rows; reserved "wappalyzer" for future sync
    enabled:    False for greyed / low-confidence recipes (test before enabling)
    synced_at:  populated only during a future Wappalyzer sync run (None for custom)
    """

    __tablename__ = "lv_fingerprint_recipe"

    id: int | None = Field(default=None, primary_key=True)
    recipe_key: str = Field(index=True, unique=True)
    category: str = Field(default="")
    tech_type: str = Field(default="")
    urlscan_query: str = Field(default="")
    publicwww_query: str = Field(default="")
    verify_fingerprints_json: str = Field(default="[]")
    id_extractors_json: str = Field(default="{}")
    exclude_hosts_json: str = Field(default="[]")
    # confidence: "high" | "medium" | "low"
    confidence: str = Field(default="high")
    enabled: bool = Field(default=True)
    # source: "custom" for catalog rows; "wappalyzer" for future synced rows
    source: str = Field(default="custom")
    license: str = Field(default="")
    synced_at: str | None = Field(default=None)
