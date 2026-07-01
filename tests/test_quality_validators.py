import inspect


def test_email_validated_requires_syntax_mx_nondisposable():
    from app.quality.validators.email import validate_email
    ok = validate_email("info@acme.com", mx_lookup=lambda d: True)
    assert ok["present"] and ok["validated"] and ok["syntax"] and ok["mx"]
    no_mx = validate_email("info@acme.com", mx_lookup=lambda d: False)
    assert no_mx["present"] and not no_mx["validated"] and not no_mx["mx"]     # no MX -> not validated
    bad = validate_email("not-an-email", mx_lookup=lambda d: True)
    assert not bad["validated"] and not bad["syntax"]
    disp = validate_email("info@mailinator.com", mx_lookup=lambda d: True)
    assert disp["disposable"] and not disp["validated"]                        # disposable -> not validated
    empty = validate_email("", mx_lookup=lambda d: True)
    assert not empty["present"] and not empty["validated"]


def test_email_validator_never_smtp_probes():   # INV-Q6
    import app.quality.validators.email as E
    src = inspect.getsource(E)
    assert "smtplib" not in src and "SMTP" not in src and "sendmail" not in src


def test_phone_validated_format_and_line_type():
    from app.quality.validators.phone import validate_phone
    m = validate_phone("+44 7911 123456")            # UK mobile
    assert m["present"] and m["validated"] and m["line_type"] == "mobile"
    bad = validate_phone("12")
    assert not bad["validated"]
    assert validate_phone("")["present"] is False


def test_address_validated_requires_geocode():
    from app.quality.validators.address import validate_address
    ok = validate_address("1 High St", "London", "SW1A 1AA", "GB", 51.5, -0.1)
    assert ok["present"] and ok["validated"] and ok["geocoded"]
    nogeo = validate_address("1 High St", "London", "SW1A 1AA", "GB", None, None)
    assert nogeo["present"] and not nogeo["validated"]     # no coords -> not validated


def test_website_and_profile_and_freshness():
    from app.quality.validators.website import validate_website
    from app.quality.validators.profile import validate_profile
    from app.quality.validators.freshness import validate_freshness
    from datetime import datetime, timezone, timedelta
    assert validate_website({"website_reachable": True})["validated"] is True
    assert validate_website({})["validated"] is False
    assert validate_profile("Acme", ["cafe"], "London", "Mo-Su", "https://a.com")["validated"] is True
    assert validate_profile("", [], "", "", "")["validated"] is False
    fresh = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    assert validate_freshness(fresh)["validated"] is True
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    assert validate_freshness(old)["validated"] is False
