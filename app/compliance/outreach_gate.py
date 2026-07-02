"""US outreach hold-gate (DNC/TCPA).

Provider strings and US-region identifiers live HERE — not in app/core — so that
the core package remains free of outreach/compliance specifics.

Invariant: all US-region leads are held from sale (blocked at preview/unlock/search)
until a DNC/TCPA clearance flag is present on the lead.  No such flag exists yet, so
*every* US lead is held.
"""
from __future__ import annotations

from app.core.serve_filters import register_serve_filter

# Normalised region codes treated as "United States" for outreach purposes.
US_REGIONS: frozenset[str] = frozenset({"US", "USA"})


def compliance_region(country: str) -> str:
    """Return a normalised compliance region string.

    "US" / "USA" (case-insensitive) → "US".
    All other values are returned as-is (uppercased so comparisons are stable).
    """
    upper = (country or "").strip().upper()
    if upper in US_REGIONS:
        return "US"
    return upper


def us_outreach_hold_filter(session, buyer_account_id, lead, ctx=None) -> bool:  # noqa: ARG001
    """Serve-filter that HOLDS US-region leads pending DNC/TCPA gate clearance.

    Returns False (HOLD) when:
      - The lead's compliance_region is "US", AND
      - The lead does not carry a cleared DNC/TCPA flag.

    There is currently no DNC/TCPA clearance flag on the Lead model, so every
    US lead is held unconditionally.

    Returns True (PASS) for all non-US leads.
    """
    region = compliance_region(getattr(lead, "country", "") or "")
    if region not in US_REGIONS:
        return True  # not a US lead → pass
    # US lead: check for a future DNC/TCPA clearance flag.
    # No such flag exists yet → all US leads are held.
    dnc_cleared = getattr(lead, "dnc_tcpa_cleared", False)
    return bool(dnc_cleared)


def register_outreach_gate() -> None:
    """Register the US outreach hold-filter into the serve-filters chain."""
    register_serve_filter(us_outreach_hold_filter)
