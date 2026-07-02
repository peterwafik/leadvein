from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel, create_engine


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class User(SQLModel, table=True):
    __tablename__ = "lv_user"
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str = ""
    role: str = "buyer"  # buyer | admin
    buyer_account_id: int | None = None
    created_at: str = Field(default_factory=_now)


class BuyerAccount(SQLModel, table=True):
    __tablename__ = "lv_buyer_account"
    id: int | None = Field(default=None, primary_key=True)
    company_name: str = ""
    credits: int = 0
    compliance_ack_at: str | None = None
    created_at: str = Field(default_factory=_now)


class LeadSource(SQLModel, table=True):
    __tablename__ = "lv_lead_source"
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
    __tablename__ = "lv_lead_category"
    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    label: str = ""
    parent_id: int | None = None


class CategoryMapping(SQLModel, table=True):
    __tablename__ = "lv_category_mapping"
    id: int | None = Field(default=None, primary_key=True)
    source_key: str = Field(index=True)
    external_value: str = Field(index=True)  # e.g. "amenity=restaurant"
    category_key: str = ""


class Lead(SQLModel, table=True):
    __tablename__ = "lv_lead"
    __table_args__ = (Index("ix_lv_lead_source_key_col", "source_key"),)
    id: int | None = Field(default=None, primary_key=True)
    business_name: str = ""
    category_keys_json: str = "[]"
    # location
    address_line1: str = ""
    city: str = Field(default="", index=True)
    region: str = ""
    postal_code: str = ""
    country: str = Field(default="", index=True)
    latitude: float | None = None
    longitude: float | None = None
    # contact (business-level only)
    phone: str = ""
    public_email: str = ""
    website_url: str = ""
    # flexible attribute + intent blobs
    attributes_json: str = "{}"
    intent_json: str = "{}"
    # validation stamp
    validation_json: str = "{}"
    completeness_score: int = Field(default=0, index=True)
    # scoring
    score_total: int = Field(default=0, index=True)
    subscores_json: str = "{}"
    score_explanation: str = ""
    scoring_profile_key: str = ""
    # source + compliance metadata
    source_key: str = ""
    source_name: str = ""
    source_url: str = ""
    source_license: str = ""
    attribution: str = ""
    lawful_basis: str = "legitimate_interest_b2b_public"
    date_discovered: str = Field(default_factory=_now)
    date_last_verified: str | None = Field(default=None, index=True)
    suppression_status: str = "clear"
    retention_expiry: str | None = None
    # marketplace
    price_credits: int = 1
    exclusivity_status: str = "non_exclusive"
    times_sold: int = 0
    last_sold_at: str | None = None
    dedupe_key: str = Field(default="", index=True)
    # per-field provenance: {field: {"source":str,"license":str,"at":str}}
    field_provenance_json: str = Field(default="{}")


class SourceBudget(SQLModel, table=True):
    __tablename__ = "lv_source_budget"
    id: int | None = Field(default=None, primary_key=True)
    source_key: str = Field(default="", index=True)
    used: int = Field(default=0)
    cap: int = Field(default=0)
    window_start: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class LeadRecipe(SQLModel, table=True):
    __tablename__ = "lv_lead_recipe"
    id: int | None = Field(default=None, primary_key=True)
    buyer_account_id: int = 0
    name: str = ""
    filters_json: str = "{}"
    scoring_profile_key: str = ""
    created_at: str = Field(default_factory=_now)


class PurchasedLead(SQLModel, table=True):
    __tablename__ = "lv_purchased_lead"
    __table_args__ = (UniqueConstraint("buyer_account_id", "lead_id",
                                       name="uq_lv_purchased_buyer_lead"),)
    id: int | None = Field(default=None, primary_key=True)
    buyer_account_id: int = Field(index=True)
    lead_id: int = Field(index=True)
    price_credits: int = 0
    status: str = "New"
    notes_json: str = "[]"
    purchased_at: str = Field(default_factory=_now)


class CreditTransaction(SQLModel, table=True):
    __tablename__ = "lv_credit_transaction"
    id: int | None = Field(default=None, primary_key=True)
    buyer_account_id: int = Field(index=True)
    delta: int = 0
    reason: str = ""
    ref: str = ""
    created_at: str = Field(default_factory=_now)


class StripePayment(SQLModel, table=True):
    __tablename__ = "lv_stripe_payment"
    __table_args__ = (UniqueConstraint("session_id", name="uq_lv_stripe_session"),)
    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(default="", index=True)
    buyer_account_id: int = Field(default=0, index=True)
    pack_key: str = ""
    credits: int = 0
    amount_cents: int = 0
    currency: str = "gbp"
    status: str = "pending"  # pending | completed
    created_at: str = Field(default_factory=_now)
    completed_at: str | None = None


class SuppressionList(SQLModel, table=True):
    __tablename__ = "lv_suppression_list"
    id: int | None = Field(default=None, primary_key=True)
    buyer_account_id: int | None = None  # null => global suppression
    name: str = ""
    created_at: str = Field(default_factory=_now)


class SuppressionEntry(SQLModel, table=True):
    __tablename__ = "lv_suppression_entry"
    id: int | None = Field(default=None, primary_key=True)
    list_id: int = Field(index=True)
    kind: str = ""  # domain | phone | email | business_name
    value: str = Field(default="", index=True)


class OptOutRequest(SQLModel, table=True):
    __tablename__ = "lv_opt_out_request"
    id: int | None = Field(default=None, primary_key=True)
    kind: str = ""  # domain | phone | email
    value: str = Field(default="", index=True)
    applied: bool = False
    created_at: str = Field(default_factory=_now)


class AuditLog(SQLModel, table=True):
    __tablename__ = "lv_audit_log"
    id: int | None = Field(default=None, primary_key=True)
    actor_user_id: int | None = None
    action: str = ""
    entity: str = ""
    entity_id: str = ""
    meta_json: str = "{}"
    created_at: str = Field(default_factory=_now)


class IngestionJob(SQLModel, table=True):
    __tablename__ = "lv_ingestion_job"
    id: int | None = Field(default=None, primary_key=True)
    adapter_key: str = ""
    query_json: str = "{}"
    status: str = "pending"
    counts_json: str = "{}"
    created_at: str = Field(default_factory=_now)


class Segment(SQLModel, table=True):
    __tablename__ = "lv_segment"
    id: int | None = Field(default=None, primary_key=True)
    buyer_account_id: int = Field(default=0, index=True)
    name: str = ""
    composition_json: str = "{}"
    origin_key: str = ""  # optional provenance (e.g. a preset key, set by the layer above)
    created_at: str = Field(default_factory=_now)
    updated_at: str | None = None


class LeadCategoryLink(SQLModel, table=True):
    __tablename__ = "lv_lead_category_link"
    id: int | None = Field(default=None, primary_key=True)
    lead_id: int = Field(index=True)
    category_key: str = Field(default="", index=True)


class AttributeCoverage(SQLModel, table=True):
    __tablename__ = "lv_attribute_coverage"
    id: int | None = Field(default=None, primary_key=True)
    path: str = Field(default="", index=True)
    populated: int = 0
    total: int = 0
    updated_at: str = Field(default_factory=_now)


def init_db(url: str = "sqlite:///leadvault.db"):
    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine
