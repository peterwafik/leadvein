from __future__ import annotations

import re

_SYNTAX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# small offline blocklist of common disposable-mail domains (extend as needed)
DISPOSABLE = {"mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
              "yopmail.com", "trashmail.com", "getnada.com", "sharklasers.com",
              "dispostable.com", "maildrop.cc"}


def _default_mx(domain: str) -> bool:
    # DNS MX lookup only. NEVER connects to a mail server (no probe) — INV-Q6.
    try:
        import dns.resolver
        return len(dns.resolver.resolve(domain, "MX")) > 0
    except Exception:
        return False


def validate_email(email: str, *, mx_lookup=_default_mx) -> dict:
    email = (email or "").strip().lower()
    if not email:
        return {"present": False, "validated": False, "syntax": False,
                "mx": False, "disposable": False}
    syntax = bool(_SYNTAX.match(email))
    domain = email.split("@", 1)[1] if "@" in email else ""
    disposable = domain in DISPOSABLE
    mx = bool(mx_lookup(domain)) if (syntax and domain and not disposable) else False
    return {"present": True, "validated": syntax and mx and not disposable,
            "syntax": syntax, "mx": mx, "disposable": disposable}
