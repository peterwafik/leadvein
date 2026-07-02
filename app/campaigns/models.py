from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Campaign(SQLModel, table=True):
    __tablename__ = "lv_campaign"

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    name: str = ""
    description: str = ""
    active: bool = True
    # JSON text columns — stored as raw strings, callers use json.loads/dumps
    composition_template: str = "{}"
    preferred: str = "[]"
    scoring_profile_key: str = ""
    quality_profile_key: str = ""
    gated_signals: str = "[]"
    param_schema: str = "{}"
    created_at: str = Field(default_factory=_now)
