"""Hunter.io domain-search enrichment adapter.

Fills a MISSING business email with a role-based address only.
Personal emails are DISCARDED (people-data guard / INV-2 allowlist).

Free tier: 25 lookups / month.  Key: LEADVAULT_HUNTER_KEY.
No live HTTP in tests — inject a fake http client.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

import requests

from app.adapters.base import FieldContribution, SourceMeta
from app.targeting.predicates.contactability import ROLE_PREFIXES, _local

_API_BASE = "https://api.hunter.io/v2"
_LICENSE = "Hunter.io API Terms"


class _RealHttp:
    """Thin requests wrapper — swapped out in tests."""

    def get(self, url: str, *, params=None, timeout=30):
        return requests.get(url, params=params, timeout=timeout)


class HunterAdapter:
    """EnrichmentAdapter: fills public_email with a role-based address via Hunter.io."""

    meta = SourceMeta(
        key="hunter",
        name="Hunter.io",
        type="email_enrichment",
        url="https://hunter.io",
        license=_LICENSE,
        terms_status="permitted",
        regions=["*"],
        key_env="LEADVAULT_HUNTER_KEY",
        free_tier={"cap": 25, "window": "month"},
    )

    def __init__(self, http=None):
        self._http = http or _RealHttp()
        self._key = os.getenv("LEADVAULT_HUNTER_KEY", "")

    # ------------------------------------------------------------------
    # EnrichmentAdapter protocol
    # ------------------------------------------------------------------

    def enrich(self, view: dict) -> list[FieldContribution]:
        """Return at most one FieldContribution for a role-based email.

        Guards:
        - No website_url / unparseable domain  → []
        - Lead already has a role-based public_email → [] (no-op)
        - Hunter returns only personal emails       → [] (discarded)

        Sets ``self.api_calls_last`` to 1 immediately before the HTTP request
        and to 0 at the top so no-HTTP short-circuits report 0 (no call made).
        """
        self.api_calls_last = 0  # reset; short-circuits below leave it 0

        # Guard: already has a role email
        existing = view.get("public_email") or ""
        if existing and _local(existing) in ROLE_PREFIXES:
            return []

        # Derive domain from website_url
        domain = _extract_domain(view.get("website_url") or "")
        if not domain:
            return []

        self.api_calls_last = 1  # about to hit the provider
        # Call Hunter domain-search (mocked in tests)
        resp = self._http.get(
            f"{_API_BASE}/domain-search",
            params={"domain": domain, "api_key": self._key},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        emails: list[dict] = (data.get("data") or {}).get("emails") or []

        # Keep only role-based addresses (INV-2 allowlist); ignore Hunter's own type field
        for entry in emails:
            address = entry.get("value") or ""
            if address and _local(address) in ROLE_PREFIXES:
                return [
                    FieldContribution(
                        field="public_email",
                        value=address,
                        license=_LICENSE,
                    )
                ]

        # No role email found — personal emails are silently discarded
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_domain(url: str) -> str:
    """Return the netloc (hostname) from a URL, or '' if unparseable / empty."""
    if not url:
        return ""
    # Add scheme if missing so urlparse works reliably
    if "://" not in url:
        url = "https://" + url
    try:
        netloc = urlparse(url).netloc
    except Exception:
        return ""
    # Strip port, strip leading "www."
    host = netloc.split(":")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host
