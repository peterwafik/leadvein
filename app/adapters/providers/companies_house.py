"""Companies House (UK) source adapter.

Company fields only — NO director / officer personal data.
Uses the official Companies House API (Open Government Licence v3.0).
Requires LEADVAULT_COMPANIES_HOUSE_KEY set in environment.
"""
from __future__ import annotations

import os
from typing import Iterable

import requests

from app.adapters.base import AdapterQuery, NormalizedLead, SourceMeta

_BASE = "https://api.company-information.service.gov.uk"

# Minimal SIC-code -> LeadVault taxonomy map.
# SIC codes are 5-digit strings; we match the first 2 digits for broad mapping.
_SIC_PREFIX_TO_CATEGORY: dict[str, str] = {
    "01": "agriculture",
    "10": "food_production",
    "11": "beverage_production",
    "41": "construction",
    "43": "construction",
    "45": "auto_repair",
    "46": "wholesale",
    "47": "retail",
    "55": "hotel",
    "56": "restaurant",
    "61": "telecommunications",
    "62": "software",
    "63": "software",
    "64": "financial_services",
    "65": "financial_services",
    "66": "financial_services",
    "68": "real_estate",
    "72": "research",
    "73": "advertising",
    "74": "consulting",
    "75": "veterinary",
    "82": "business_services",
    "85": "education",
    "86": "medical_clinic",
    "87": "care_home",
    "88": "social_work",
    "90": "arts",
    "92": "entertainment",
    "93": "gym",
    "94": "membership_organisation",
    "95": "auto_repair",
    "96": "personal_services",
}

_LICENSE = "Companies House data / Open Government Licence v3.0"


def _sic_to_categories(sic_codes: list[str]) -> list[str]:
    """Map a list of SIC codes to LeadVault category keys."""
    cats: list[str] = []
    seen: set[str] = set()
    for code in sic_codes or []:
        prefix = str(code).zfill(5)[:2]
        cat = _SIC_PREFIX_TO_CATEGORY.get(prefix, "business")
        if cat not in seen:
            seen.add(cat)
            cats.append(cat)
    return cats or ["business"]


class _RealHttp:
    """Thin wrapper around requests for injectable-http compatibility."""

    def get(self, url: str, *, auth=None, params=None, timeout=30):
        return requests.get(url, auth=auth, params=params, timeout=timeout)


class CompaniesHouseAdapter:
    meta = SourceMeta(
        key="companies_house",
        name="Companies House",
        type="registry",
        url=_BASE,
        license=_LICENSE,
        terms_status="permitted",
        regions=["GB"],
        key_env="LEADVAULT_COMPANIES_HOUSE_KEY",
        rate_limit={"per": 600, "seconds": 300},
    )

    def __init__(self, http=None):
        self._http = http or _RealHttp()
        self._key = os.getenv("LEADVAULT_COMPANIES_HOUSE_KEY", "")

    # ------------------------------------------------------------------
    # LeadSourceAdapter protocol
    # ------------------------------------------------------------------

    def discover(self, query: AdapterQuery) -> Iterable[dict]:
        """Search Companies House and yield raw company item dicts."""
        term = (
            query.extra.get("search_term")
            or query.area.get("city")
            or query.area.get("region")
            or ""
        )
        resp = self._http.get(
            f"{_BASE}/search/companies",
            auth=(self._key, ""),
            params={"q": term},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        yield from data.get("items", [])

    def normalize(self, raw: dict) -> NormalizedLead | None:
        """Convert a raw CH company item to a NormalizedLead.

        COMPANY FIELDS ONLY — officers / links.officers are never read.
        """
        name = raw.get("company_name")
        if not name:
            return None

        addr_raw = raw.get("registered_office_address") or {}
        address = {
            "line1": " ".join(
                x for x in (
                    addr_raw.get("address_line_1"),
                    addr_raw.get("address_line_2"),
                ) if x
            ),
            "city": addr_raw.get("locality", ""),
            "region": addr_raw.get("region", ""),
            "postal_code": addr_raw.get("postal_code", ""),
            "country": addr_raw.get("country", "GB"),
        }

        sic_codes: list[str] = raw.get("sic_codes") or []
        category_keys = _sic_to_categories(sic_codes)

        company_number = raw.get("company_number", "")
        source_url = (
            f"{_BASE}/company/{company_number}" if company_number else _BASE
        )

        return NormalizedLead(
            business_name=name,
            category_keys=category_keys,
            address=address,
            phone="",
            public_email="",
            website_url="",
            opening_hours="",
            attributes={
                "incorporation_date": raw.get("date_of_creation", ""),
                "company_status": raw.get("company_status", ""),
                "sic_codes": sic_codes,
                "company_number": company_number,
            },
            source_key=self.meta.key,
            source_url=source_url,
            source_license=self.meta.license,
            raw_ref=company_number,
        )

    def attribution(self) -> str:
        return (
            "Contains public sector information licensed under the "
            "Open Government Licence v3.0 "
            "(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). "
            "Source: Companies House (https://find-and-update.company-information.service.gov.uk/)."
        )
