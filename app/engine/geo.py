"""Best-effort country inference for a scraped lead.

Layered signals (highest confidence first):
  1. schema.org PostalAddress `addressCountry` (extracted in enrich.analyse)
  2. country-code TLD of the website (.co.uk -> GB, .de -> DE, ...)
  3. phone country code from an extracted phone (+44 -> GB, +1 -> US, ...)

All pure functions — no network, no imports beyond stdlib. ISO-3166 alpha-2 codes.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

# country-code TLDs we care about (two-label suffixes checked before one-label)
CCTLD = {
    "co.uk": "GB", "org.uk": "GB", "ac.uk": "GB", "me.uk": "GB", "uk": "GB",
    "com.au": "AU", "net.au": "AU", "org.au": "AU", "au": "AU",
    "co.nz": "NZ", "nz": "NZ", "ie": "IE", "ca": "CA", "us": "US",
    "de": "DE", "fr": "FR", "es": "ES", "it": "IT", "nl": "NL", "be": "BE",
    "ch": "CH", "at": "AT", "se": "SE", "no": "NO", "dk": "DK", "fi": "FI",
    "pt": "PT", "pl": "PL", "gr": "GR", "ro": "RO", "cz": "CZ", "hu": "HU",
    "in": "IN", "sg": "SG", "ae": "AE", "za": "ZA", "br": "BR", "mx": "MX",
    "jp": "JP", "co.za": "ZA", "com.br": "BR", "com.mx": "MX",
}

# international dialing code -> country (try longest prefix first)
PHONE_CC = {
    "44": "GB", "49": "DE", "33": "FR", "34": "ES", "39": "IT", "31": "NL",
    "32": "BE", "41": "CH", "43": "AT", "46": "SE", "47": "NO", "45": "DK",
    "358": "FI", "351": "PT", "48": "PL", "30": "GR", "40": "RO", "420": "CZ",
    "36": "HU", "353": "IE", "61": "AU", "64": "NZ", "1": "US", "91": "IN",
    "65": "SG", "971": "AE", "27": "ZA", "55": "BR", "52": "MX", "81": "JP",
}

# free-text country names / aliases -> ISO-2 (for the Country input + schema text)
_ALIASES = {
    "uk": "GB", "u.k.": "GB", "united kingdom": "GB", "great britain": "GB",
    "britain": "GB", "england": "GB", "scotland": "GB", "wales": "GB", "gb": "GB",
    "us": "US", "u.s.": "US", "usa": "US", "u.s.a.": "US", "united states": "US",
    "united states of america": "US", "america": "US",
    "germany": "DE", "deutschland": "DE", "de": "DE",
    "france": "FR", "fr": "FR", "spain": "ES", "es": "ES", "italy": "IT", "it": "IT",
    "netherlands": "NL", "nl": "NL", "belgium": "BE", "be": "BE",
    "ireland": "IE", "ie": "IE", "switzerland": "CH", "ch": "CH",
    "austria": "AT", "at": "AT", "canada": "CA", "ca": "CA",
    "australia": "AU", "au": "AU", "new zealand": "NZ", "nz": "NZ",
    "sweden": "SE", "norway": "NO", "denmark": "DK", "finland": "FI",
    "portugal": "PT", "poland": "PL", "greece": "GR", "romania": "RO",
    "india": "IN", "singapore": "SG", "south africa": "ZA", "brazil": "BR",
    "mexico": "MX", "japan": "JP",
}

_ISO2 = set(CCTLD.values()) | set(PHONE_CC.values()) | set(_ALIASES.values())


def normalize_country(value: str) -> str:
    """Map a country name / alias / ISO-2 code to an ISO-2 code ('' if unknown)."""
    if not value:
        return ""
    s = str(value).strip().lower()
    if len(s) == 2 and s.upper() in _ISO2:
        return s.upper()
    if s in _ALIASES:
        return _ALIASES[s]
    # schema sometimes gives a URL like https://schema.org/.. or "GB"
    s2 = s.strip("/").split("/")[-1]
    if len(s2) == 2 and s2.upper() in _ISO2:
        return s2.upper()
    return ""


def country_from_tld(url: str) -> str:
    host = urlsplit(url if "//" in url else "https://" + url).netloc.lower()
    host = host.split(":")[0]
    labels = host.split(".")
    if len(labels) >= 2:
        two = ".".join(labels[-2:])
        if two in CCTLD:
            return CCTLD[two]
    if labels:
        one = labels[-1]
        if one in CCTLD:
            return CCTLD[one]
    return ""


def country_from_phone(phone: str) -> str:
    if not phone:
        return ""
    s = phone.strip()
    if s.startswith("+"):
        digits = re.sub(r"\D", "", s)
    elif s.startswith("00"):
        digits = re.sub(r"\D", "", s)[2:]  # 00 international prefix
    else:
        return ""  # national format — not reliably attributable
    for n in (3, 2, 1):
        if len(digits) > n and digits[:n] in PHONE_CC:
            return PHONE_CC[digits[:n]]
    return ""


def infer_country(url: str, lead) -> dict:
    """Return {country, confidence, signals} for a lead (duck-typed: .country, .phones)."""
    schema = normalize_country(getattr(lead, "country", "") or "")
    tld = country_from_tld(url or getattr(lead, "website", "") or "")
    phone_c = ""
    for p in (getattr(lead, "phones", None) or []):
        phone_c = country_from_phone(p)
        if phone_c:
            break
    signals = {"schema": schema, "tld": tld, "phone": phone_c}
    if schema:
        return {"country": schema, "confidence": "high", "signals": signals}
    if tld:
        return {"country": tld, "confidence": "high", "signals": signals}
    if phone_c:
        return {"country": phone_c, "confidence": "medium", "signals": signals}
    return {"country": "", "confidence": "unknown", "signals": signals}


def geo_keep(target: str, inferred: str, strict: bool) -> bool:
    """Filter decision: keep a lead given the target country and its inferred country."""
    if not target:
        return True            # no geo filter
    if inferred == target:
        return True            # positively in-country
    if not inferred:
        return not strict      # unknown: keep unless strict
    return False               # positively a DIFFERENT country
