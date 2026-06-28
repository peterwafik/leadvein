from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, create_engine


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str = ""
    role: str = "buyer"  # buyer | admin
    buyer_account_id: int | None = None
    created_at: str = Field(default_factory=_now)


class BuyerAccount(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    company_name: str = ""
    credits: int = 0
    compliance_ack_at: str | None = None
    created_at: str = Field(default_factory=_now)


class LeadSource(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    name: str = ""
    type: str = ""
    url: str = ""
    license: str = ""
    terms_status: str = "permitted"
    regions_json: str = "[]"
    active: bool = True


class LeadCategory(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    label: str = ""
    parent_id: int | None = None


class CategoryMapping(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    source_key: str = Field(index=True)
    external_value: str = Field(index=True)  # e.g. "amenity=restaurant"
    category_key: str = ""


class Lead(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    business_name: str = ""
    category_keys_json: str = "[]"
    # location
    address_line1: str = ""
    city: str = ""
    region: str = ""
    postal_code: str = ""
    country: str = ""
    latitude: float | None = None
    longitude: float | None = None
    # contact (business-level only)
    phone: str = ""
    public_email: str = ""
    website_url: str = ""
    # flexible attribute + intent blobs
    attributes_json: str = "{}"
    intent_json: str = "{}"
    # scoring
    score_total: int = 0
    subscores_json: str = "{}"
    score_explanation: str = ""
    scoring_profile_key: str = ""
    # source + compliance metadata
    source_key: str = ""
    source_name: str = ""
    source_url: str = ""
    source_license: str = ""
    lawful_basis: str = "legitimate_interest_b2b_public"
    date_discovered: str = Field(default_factory=_now)
    date_last_verified: str | None = None
    opt_out_status: str = "clear"        # clear | opted_out
    suppression_status: str = "clear"
    retention_expiry: str | None = None
    # marketplace
    price_credits: int = 1
    exclusivity_status: str = "non_exclusive"
    times_sold: int = 0
    last_sold_at: str | None = None
    dedupe_key: str = Field(default="", index=True)


class LeadRecipe(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    buyer_account_id: int = 0
    name: str = ""
    filters_json: str = "{}"
    scoring_profile_key: str = ""
    created_at: str = Field(default_factory=_now)


class PurchasedLead(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    buyer_account_id: int = Field(index=True)
    lead_id: int = Field(index=True)
    price_credits: int = 0
    status: str = "New"
    notes_json: str = "[]"
    purchased_at: str = Field(default_factory=_now)


class CreditTransaction(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    buyer_account_id: int = Field(index=True)
    delta: int = 0
    reason: str = ""
    ref: str = ""
    created_at: str = Field(default_factory=_now)


class SuppressionList(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    buyer_account_id: int | None = None  # null => global suppression
    name: str = ""
    created_at: str = Field(default_factory=_now)


class SuppressionEntry(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    list_id: int = Field(index=True)
    kind: str = ""  # domain | phone | email | business_name
    value: str = Field(default="", index=True)


class OptOutRequest(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    kind: str = ""  # domain | phone | email
    value: str = Field(default="", index=True)
    applied: bool = False
    created_at: str = Field(default_factory=_now)


class AuditLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    actor_user_id: int | None = None
    action: str = ""
    entity: str = ""
    entity_id: str = ""
    meta_json: str = "{}"
    created_at: str = Field(default_factory=_now)


class IngestionJob(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    adapter_key: str = ""
    query_json: str = "{}"
    status: str = "pending"
    counts_json: str = "{}"
    created_at: str = Field(default_factory=_now)


def init_db(url: str = "sqlite:///leadvault.db"):
    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine
