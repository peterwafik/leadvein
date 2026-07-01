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
