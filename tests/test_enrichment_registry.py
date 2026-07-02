"""Task 1: EnrichmentAdapter protocol + feature-flag registry tests.

Covers:
- enabled() returns False when key_env is set but the env var is absent
- enabled() returns True when the env var is present (monkeypatched)
- A keyless adapter (key_env="") is always enabled
- list_status() surfaces terms_status, including "restricted" adapters
"""
from __future__ import annotations

import os

import pytest

from app.adapters.base import SourceMeta, FieldContribution, EnrichmentAdapter
from app.adapters import registry


# ---------------------------------------------------------------------------
# Fake adapters
# ---------------------------------------------------------------------------

class FakeKeyed:
    """Enrichment adapter that requires LEADVAULT_FAKE_KEY in env."""
    meta = SourceMeta(
        key="fake_keyed",
        name="Fake Keyed",
        type="enrichment",
        url="https://example.com",
        license="COMMERCIAL",
        terms_status="permitted",
        key_env="LEADVAULT_FAKE_KEY",
        free_tier={},
        rate_limit={},
    )

    def enrich(self, view: dict) -> list[FieldContribution]:
        return []


class FakeKeyless:
    """Enrichment adapter with no API key requirement."""
    meta = SourceMeta(
        key="fake_keyless",
        name="Fake Keyless",
        type="enrichment",
        url="https://example.com/free",
        license="PUBLIC_DOMAIN",
        terms_status="permitted",
        key_env="",
    )

    def enrich(self, view: dict) -> list[FieldContribution]:
        return [FieldContribution(field="industry", value="tech", license="PUBLIC_DOMAIN")]


class FakeRestricted:
    """Enrichment adapter with restricted terms."""
    meta = SourceMeta(
        key="fake_restricted",
        name="Fake Restricted",
        type="enrichment",
        url="https://example.com/restricted",
        license="RESTRICTED",
        terms_status="restricted",
        key_env="LEADVAULT_RESTRICTED_KEY",
    )

    def enrich(self, view: dict) -> list[FieldContribution]:
        return []


# ---------------------------------------------------------------------------
# enabled() tests
# ---------------------------------------------------------------------------

def test_keyed_adapter_disabled_without_env_var(monkeypatch):
    """A keyed adapter is disabled when the env var is not set."""
    monkeypatch.delenv("LEADVAULT_FAKE_KEY", raising=False)
    assert registry.enabled(FakeKeyed()) is False


def test_keyed_adapter_enabled_with_env_var(monkeypatch):
    """A keyed adapter is enabled when the env var is set."""
    monkeypatch.setenv("LEADVAULT_FAKE_KEY", "sk-test-1234")
    assert registry.enabled(FakeKeyed()) is True


def test_keyless_adapter_always_enabled(monkeypatch):
    """An adapter with key_env='' is always enabled regardless of env."""
    monkeypatch.delenv("LEADVAULT_FAKE_KEY", raising=False)
    assert registry.enabled(FakeKeyless()) is True


# ---------------------------------------------------------------------------
# list_status() tests
# ---------------------------------------------------------------------------

def test_list_status_surfaces_terms_status():
    """list_status() returns a dict per adapter including terms_status."""
    # Use a fresh isolated registry snapshot by registering into a local copy
    # We test by registering our fakes and checking the output contains them.
    registry.register(FakeKeyed())
    registry.register(FakeKeyless())
    registry.register(FakeRestricted())

    statuses = registry.list_status()
    by_key = {s["key"]: s for s in statuses}

    assert "fake_keyed" in by_key
    assert "fake_keyless" in by_key
    assert "fake_restricted" in by_key

    assert by_key["fake_restricted"]["terms_status"] == "restricted"
    assert by_key["fake_keyless"]["terms_status"] == "permitted"


def test_list_status_includes_required_fields(monkeypatch):
    """list_status() entries contain key, name, type, enabled, terms_status, free_tier."""
    monkeypatch.delenv("LEADVAULT_FAKE_KEY", raising=False)
    registry.register(FakeKeyed())

    statuses = registry.list_status()
    by_key = {s["key"]: s for s in statuses}
    entry = by_key["fake_keyed"]

    assert "key" in entry
    assert "name" in entry
    assert "type" in entry
    assert "enabled" in entry
    assert "terms_status" in entry
    assert "free_tier" in entry
    assert entry["enabled"] is False


def test_list_status_accepts_session_param():
    """list_status(session=None) must accept an optional session without error."""
    result = registry.list_status(session=None)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# FieldContribution dataclass
# ---------------------------------------------------------------------------

def test_field_contribution_defaults():
    fc = FieldContribution(field="email", value="a@b.com", license="CC0")
    assert fc.confidence == 1.0


def test_field_contribution_custom_confidence():
    fc = FieldContribution(field="phone", value="+1555", license="CC0", confidence=0.85)
    assert fc.confidence == 0.85


# ---------------------------------------------------------------------------
# EnrichmentAdapter structural protocol check
# ---------------------------------------------------------------------------

def test_enrichment_adapter_protocol():
    """FakeKeyed satisfies the EnrichmentAdapter Protocol structurally."""
    adapter = FakeKeyed()
    assert isinstance(adapter, EnrichmentAdapter)
