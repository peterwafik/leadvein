"""Tests for the Hunter.io enrichment adapter (Task 5).

TDD: tests are written fail-first, then HunterAdapter is implemented.

NO live HTTP — all network traffic is intercepted by FakeHttp.

Covers:
(a) Canned response with both a personal and a role email → only the role
    email is returned as a FieldContribution.
(b) Canned response with only personal emails → [] (discarded).
(c) View with no website_url / no parseable domain → [].
(d) View that already carries a role-based public_email → [] (no-op).
"""
from __future__ import annotations

import pytest

from app.adapters.providers.hunter import HunterAdapter
from app.adapters.base import FieldContribution


# ---------------------------------------------------------------------------
# Fake HTTP plumbing
# ---------------------------------------------------------------------------

class FakeResp:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        pass  # always 200 in tests

    def json(self):
        return self._payload


class FakeHttp:
    """Records calls, returns a canned payload — zero real network I/O."""

    def __init__(self, payload: dict):
        self._payload = payload
        self.calls: list[dict] = []

    def get(self, url: str, *, params=None, timeout=30):
        self.calls.append({"url": url, "params": params})
        return FakeResp(self._payload)


# ---------------------------------------------------------------------------
# Canned Hunter API responses
# ---------------------------------------------------------------------------

# Response containing BOTH a personal email and a role email
MIXED_RESPONSE = {
    "data": {
        "emails": [
            {"value": "john.smith@acme.com", "type": "personal"},
            {"value": "sales@acme.com",       "type": "generic"},
        ]
    }
}

# Response containing ONLY personal emails
PERSONAL_ONLY_RESPONSE = {
    "data": {
        "emails": [
            {"value": "john.smith@acme.com", "type": "personal"},
            {"value": "jane.doe@acme.com",   "type": "personal"},
        ]
    }
}

# Response with zero emails
EMPTY_RESPONSE = {"data": {"emails": []}}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_adapter(payload: dict) -> HunterAdapter:
    return HunterAdapter(http=FakeHttp(payload))


def _view(website_url: str = "https://acme.com", public_email: str = "") -> dict:
    return {"website_url": website_url, "public_email": public_email}


# ---------------------------------------------------------------------------
# (a) Mixed response: personal + role → only role email returned
# ---------------------------------------------------------------------------

def test_mixed_response_returns_only_role_email():
    adapter = _make_adapter(MIXED_RESPONSE)
    result = adapter.enrich(_view())
    assert len(result) == 1
    assert isinstance(result[0], FieldContribution)
    assert result[0].field == "public_email"
    assert result[0].value == "sales@acme.com"
    assert result[0].license == "Hunter.io API Terms"


def test_personal_email_is_not_returned_in_mixed_response():
    adapter = _make_adapter(MIXED_RESPONSE)
    result = adapter.enrich(_view())
    values = [c.value for c in result]
    assert "john.smith@acme.com" not in values


# ---------------------------------------------------------------------------
# (b) Personal-only response → [] (all discarded)
# ---------------------------------------------------------------------------

def test_personal_only_response_returns_empty():
    adapter = _make_adapter(PERSONAL_ONLY_RESPONSE)
    result = adapter.enrich(_view())
    assert result == []


# ---------------------------------------------------------------------------
# (c) No domain → [] (no HTTP call made)
# ---------------------------------------------------------------------------

def test_no_website_url_returns_empty():
    http = FakeHttp(MIXED_RESPONSE)
    adapter = HunterAdapter(http=http)
    result = adapter.enrich({"website_url": "", "public_email": ""})
    assert result == []
    assert http.calls == []  # must NOT have called the API


def test_missing_website_url_key_returns_empty():
    http = FakeHttp(MIXED_RESPONSE)
    adapter = HunterAdapter(http=http)
    result = adapter.enrich({"public_email": ""})
    assert result == []
    assert http.calls == []


# ---------------------------------------------------------------------------
# (d) Lead already has a role email → [] (no-op, no HTTP call)
# ---------------------------------------------------------------------------

def test_already_has_role_email_returns_empty():
    http = FakeHttp(MIXED_RESPONSE)
    adapter = HunterAdapter(http=http)
    result = adapter.enrich(_view(public_email="info@acme.com"))
    assert result == []
    assert http.calls == []  # must NOT have called the API


# ---------------------------------------------------------------------------
# Domain extraction edge cases
# ---------------------------------------------------------------------------

def test_www_prefix_stripped():
    """www.acme.com should be resolved as acme.com (domain passed to Hunter)."""
    http = FakeHttp(EMPTY_RESPONSE)
    adapter = HunterAdapter(http=http)
    adapter.enrich(_view(website_url="https://www.acme.com/about"))
    assert http.calls[0]["params"]["domain"] == "acme.com"


def test_path_stripped_from_domain():
    http = FakeHttp(EMPTY_RESPONSE)
    adapter = HunterAdapter(http=http)
    adapter.enrich(_view(website_url="http://acme.com/contact-us"))
    assert http.calls[0]["params"]["domain"] == "acme.com"


def test_schemeless_url_handled():
    """A URL without a scheme (e.g. 'acme.com') must still work."""
    http = FakeHttp(EMPTY_RESPONSE)
    adapter = HunterAdapter(http=http)
    adapter.enrich(_view(website_url="acme.com"))
    assert http.calls[0]["params"]["domain"] == "acme.com"


# ---------------------------------------------------------------------------
# Meta assertions
# ---------------------------------------------------------------------------

def test_meta_key():
    assert HunterAdapter.meta.key == "hunter"


def test_meta_key_env():
    assert HunterAdapter.meta.key_env == "LEADVAULT_HUNTER_KEY"


def test_meta_free_tier():
    ft = HunterAdapter.meta.free_tier
    assert ft["cap"] == 25
    assert ft["window"] == "month"


def test_meta_license():
    assert HunterAdapter.meta.license == "Hunter.io API Terms"
