from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol, runtime_checkable


@dataclass
class SourceMeta:
    key: str
    name: str
    type: str
    url: str
    license: str
    terms_status: str = "permitted"
    regions: list = field(default_factory=lambda: ["*"])


@dataclass
class AdapterQuery:
    area: dict
    categories: list
    limit: int = 100
    extra: dict = field(default_factory=dict)
    country: str = ""


@dataclass
class NormalizedLead:
    business_name: str
    category_keys: list
    address: dict
    phone: str = ""
    public_email: str = ""
    website_url: str = ""
    opening_hours: str = ""
    attributes: dict = field(default_factory=dict)
    source_key: str = ""
    source_url: str = ""
    source_license: str = ""
    raw_ref: str = ""


@runtime_checkable
class LeadSourceAdapter(Protocol):
    meta: SourceMeta

    def discover(self, query: AdapterQuery) -> Iterable[dict]: ...
    def normalize(self, raw: dict) -> "NormalizedLead | None": ...
    def attribution(self) -> str: ...
