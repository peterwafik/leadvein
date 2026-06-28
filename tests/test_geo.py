from dataclasses import dataclass, field

from app.engine.geo import (normalize_country, country_from_tld,
                            country_from_phone, infer_country, geo_keep)


@dataclass
class FakeLead:
    website: str = ""
    country: str = ""
    phones: list = field(default_factory=list)


def test_normalize_country_aliases_and_codes():
    assert normalize_country("UK") == "GB"
    assert normalize_country("United Kingdom") == "GB"
    assert normalize_country("us") == "US"
    assert normalize_country("Germany") == "DE"
    assert normalize_country("GB") == "GB"
    assert normalize_country("") == ""
    assert normalize_country("Atlantis") == ""


def test_country_from_tld():
    assert country_from_tld("https://marios.co.uk/") == "GB"
    assert country_from_tld("https://shop.de/") == "DE"
    assert country_from_tld("https://example.com.au/") == "AU"
    assert country_from_tld("https://foo.com/") == ""   # gTLD -> unknown
    assert country_from_tld("https://thing.io/") == ""


def test_country_from_phone():
    assert country_from_phone("+44 23 9248 2819") == "GB"
    assert country_from_phone("+1-555-123-4567") == "US"
    assert country_from_phone("+49 3695 604282") == "DE"
    assert country_from_phone("+353 1 234 5678") == "IE"
    assert country_from_phone("0044 20 1234 5678") == "GB"  # 00 intl prefix
    assert country_from_phone("0492 432 124") == ""         # national -> unknown


def test_infer_country_priority():
    # schema wins (high)
    assert infer_country("https://x.com/", FakeLead(country="United Kingdom"))["country"] == "GB"
    # tld wins when no schema
    assert infer_country("https://x.co.uk/", FakeLead())["country"] == "GB"
    # phone used when no schema/tld (medium)
    r = infer_country("https://x.com/", FakeLead(phones=["+49 30 123456"]))
    assert r["country"] == "DE" and r["confidence"] == "medium"
    # nothing -> unknown
    assert infer_country("https://x.com/", FakeLead())["country"] == ""


def test_geo_keep_lenient_and_strict():
    # no target -> always keep
    assert geo_keep("", "GB", False) is True
    # in-country -> keep
    assert geo_keep("GB", "GB", False) is True
    # different country -> drop (both modes)
    assert geo_keep("GB", "US", False) is False
    assert geo_keep("GB", "US", True) is False
    # unknown -> keep when lenient, drop when strict
    assert geo_keep("GB", "", False) is True
    assert geo_keep("GB", "", True) is False
