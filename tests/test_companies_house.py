"""Tests for the Companies House source adapter.

No live HTTP calls — all network traffic is intercepted by FakeHttp.
"""
from __future__ import annotations

import json

import pytest

from app.adapters.base import AdapterQuery
from app.adapters.providers.companies_house import CompaniesHouseAdapter, _LICENSE

# ---------------------------------------------------------------------------
# Canned Companies House search response
# The response intentionally includes an 'officers' field to verify it is
# completely ignored by the adapter.
# ---------------------------------------------------------------------------
CANNED_SEARCH_RESPONSE = {
    "items": [
        {
            "company_name": "ACME WIDGETS LTD",
            "company_number": "12345678",
            "company_status": "active",
            "date_of_creation": "2010-03-15",
            "sic_codes": ["47910", "62010"],
            "registered_office_address": {
                "address_line_1": "10 Baker Street",
                "address_line_2": "Suite 4",
                "locality": "London",
                "region": "Greater London",
                "postal_code": "W1U 3BW",
                "country": "England",
            },
            # Officers field MUST be ignored — it contains personal data
            "officers": [
                {"name": "SMITH, John Edward", "officer_role": "director"},
            ],
            # links also contains officer references — must be ignored
            "links": {
                "self": "/company/12345678",
                "officers": "/company/12345678/officers",
                "filing_history": "/company/12345678/filing-history",
            },
        }
    ],
    "hits": 1,
}


# ---------------------------------------------------------------------------
# Fake HTTP client (injectable)
# ---------------------------------------------------------------------------
class FakeResp:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        pass  # always succeeds in tests

    def json(self):
        return self._payload


class FakeHttp:
    """Records calls and returns canned responses — zero real network I/O."""

    def __init__(self, payload: dict):
        self._payload = payload
        self.calls: list[dict] = []

    def get(self, url: str, *, auth=None, params=None, timeout=30):
        self.calls.append({"url": url, "auth": auth, "params": params})
        return FakeResp(self._payload)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_adapter(payload=None) -> CompaniesHouseAdapter:
    http = FakeHttp(payload or CANNED_SEARCH_RESPONSE)
    return CompaniesHouseAdapter(http=http)


# ---------------------------------------------------------------------------
# discover() tests
# ---------------------------------------------------------------------------

def test_discover_yields_items():
    adapter = _make_adapter()
    query = AdapterQuery(area={"city": "London"}, categories=["retail"])
    items = list(adapter.discover(query))
    assert len(items) == 1
    assert items[0]["company_name"] == "ACME WIDGETS LTD"


def test_discover_sends_basic_auth_with_empty_password(monkeypatch):
    """Auth tuple must be (api_key, "")."""
    monkeypatch.setenv("LEADVAULT_COMPANIES_HOUSE_KEY", "test-key-abc")
    http = FakeHttp(CANNED_SEARCH_RESPONSE)
    adapter = CompaniesHouseAdapter(http=http)
    query = AdapterQuery(area={"city": "London"}, categories=[])
    list(adapter.discover(query))
    assert http.calls[0]["auth"] == ("test-key-abc", "")


def test_discover_uses_area_city_as_search_term():
    http = FakeHttp(CANNED_SEARCH_RESPONSE)
    adapter = CompaniesHouseAdapter(http=http)
    query = AdapterQuery(area={"city": "Manchester"}, categories=[])
    list(adapter.discover(query))
    assert http.calls[0]["params"]["q"] == "Manchester"


def test_discover_prefers_extra_search_term_over_city():
    http = FakeHttp(CANNED_SEARCH_RESPONSE)
    adapter = CompaniesHouseAdapter(http=http)
    query = AdapterQuery(
        area={"city": "London"},
        categories=[],
        extra={"search_term": "widget manufacturer"},
    )
    list(adapter.discover(query))
    assert http.calls[0]["params"]["q"] == "widget manufacturer"


def test_discover_empty_items():
    adapter = _make_adapter({"items": [], "hits": 0})
    query = AdapterQuery(area={"city": "London"}, categories=[])
    assert list(adapter.discover(query)) == []


# ---------------------------------------------------------------------------
# normalize() tests
# ---------------------------------------------------------------------------

def test_normalize_returns_normalized_lead():
    adapter = _make_adapter()
    raw = CANNED_SEARCH_RESPONSE["items"][0]
    lead = adapter.normalize(raw)
    assert lead is not None


def test_normalize_business_name():
    adapter = _make_adapter()
    raw = CANNED_SEARCH_RESPONSE["items"][0]
    lead = adapter.normalize(raw)
    assert lead.business_name == "ACME WIDGETS LTD"


def test_normalize_address():
    adapter = _make_adapter()
    raw = CANNED_SEARCH_RESPONSE["items"][0]
    lead = adapter.normalize(raw)
    assert "Baker Street" in lead.address["line1"]
    assert lead.address["city"] == "London"
    assert lead.address["postal_code"] == "W1U 3BW"
    assert lead.address["country"] == "England"


def test_normalize_sic_derived_category():
    """SIC 47910 -> prefix 47 -> retail; 62010 -> prefix 62 -> software."""
    adapter = _make_adapter()
    raw = CANNED_SEARCH_RESPONSE["items"][0]
    lead = adapter.normalize(raw)
    # At least one of the mapped categories must be present
    assert "retail" in lead.category_keys or "software" in lead.category_keys


def test_normalize_fallback_category_when_no_sic():
    adapter = _make_adapter()
    raw = {
        "company_name": "NO SIC CO LTD",
        "company_number": "99999999",
        "company_status": "active",
        "date_of_creation": "2020-01-01",
        "sic_codes": [],
        "registered_office_address": {"locality": "Leeds"},
    }
    lead = adapter.normalize(raw)
    assert lead is not None
    assert lead.category_keys == ["business"]


def test_normalize_attributes():
    adapter = _make_adapter()
    raw = CANNED_SEARCH_RESPONSE["items"][0]
    lead = adapter.normalize(raw)
    assert lead.attributes["incorporation_date"] == "2010-03-15"
    assert lead.attributes["company_status"] == "active"
    assert lead.attributes["company_number"] == "12345678"
    assert lead.attributes["sic_codes"] == ["47910", "62010"]


def test_normalize_phone_is_empty():
    adapter = _make_adapter()
    raw = CANNED_SEARCH_RESPONSE["items"][0]
    lead = adapter.normalize(raw)
    assert lead.phone == ""


def test_normalize_public_email_is_empty():
    adapter = _make_adapter()
    raw = CANNED_SEARCH_RESPONSE["items"][0]
    lead = adapter.normalize(raw)
    assert lead.public_email == ""


def test_normalize_source_key():
    adapter = _make_adapter()
    raw = CANNED_SEARCH_RESPONSE["items"][0]
    lead = adapter.normalize(raw)
    assert lead.source_key == "companies_house"


def test_normalize_source_license_is_ogl():
    adapter = _make_adapter()
    raw = CANNED_SEARCH_RESPONSE["items"][0]
    lead = adapter.normalize(raw)
    assert "Open Government Licence" in lead.source_license


def test_normalize_no_officer_personal_data():
    """Officers must NEVER appear anywhere in the NormalizedLead."""
    adapter = _make_adapter()
    raw = CANNED_SEARCH_RESPONSE["items"][0]
    lead = adapter.normalize(raw)

    # Serialise the whole lead to a string to catch any leakage
    lead_str = json.dumps(
        {
            "business_name": lead.business_name,
            "category_keys": lead.category_keys,
            "address": lead.address,
            "phone": lead.phone,
            "public_email": lead.public_email,
            "website_url": lead.website_url,
            "opening_hours": lead.opening_hours,
            "attributes": lead.attributes,
            "source_key": lead.source_key,
            "source_url": lead.source_url,
            "source_license": lead.source_license,
            "raw_ref": lead.raw_ref,
        }
    )

    # Officer name must not appear
    assert "SMITH" not in lead_str
    assert "John Edward" not in lead_str
    assert "director" not in lead_str
    assert "officers" not in lead_str.lower()


def test_normalize_returns_none_when_no_name():
    adapter = _make_adapter()
    lead = adapter.normalize({"company_number": "99999999"})
    assert lead is None


# ---------------------------------------------------------------------------
# attribution() tests
# ---------------------------------------------------------------------------

def test_attribution_contains_ogl():
    adapter = _make_adapter()
    attr = adapter.attribution()
    assert "Open Government Licence" in attr


def test_attribution_contains_companies_house():
    adapter = _make_adapter()
    attr = adapter.attribution()
    assert "Companies House" in attr


# ---------------------------------------------------------------------------
# meta tests
# ---------------------------------------------------------------------------

def test_meta_key():
    assert CompaniesHouseAdapter.meta.key == "companies_house"


def test_meta_regions_gb():
    assert "GB" in CompaniesHouseAdapter.meta.regions


def test_meta_key_env():
    assert CompaniesHouseAdapter.meta.key_env == "LEADVAULT_COMPANIES_HOUSE_KEY"


def test_meta_license_ogl():
    assert "Open Government Licence" in CompaniesHouseAdapter.meta.license


def test_meta_rate_limit():
    rl = CompaniesHouseAdapter.meta.rate_limit
    assert rl.get("per") == 600
    assert rl.get("seconds") == 300
