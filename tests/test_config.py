import pytest
import app.core.config as cfg


def test_env_and_is_prod(monkeypatch):
    monkeypatch.delenv("LEADVAULT_ENV", raising=False)
    assert cfg.env() == "dev" and cfg.is_prod() is False
    monkeypatch.setenv("LEADVAULT_ENV", "prod")
    assert cfg.is_prod() is True


def test_secret_dev_default_ok_but_prod_requires_strong(monkeypatch):
    monkeypatch.delenv("LEADVAULT_ENV", raising=False)
    monkeypatch.delenv("LEADVAULT_SECRET", raising=False)
    assert cfg.secret() == cfg.DEV_SECRET            # dev: default allowed
    monkeypatch.setenv("LEADVAULT_ENV", "prod")
    with pytest.raises(RuntimeError):                # prod + default/unset secret -> refuse
        cfg.secret()
    monkeypatch.setenv("LEADVAULT_SECRET", "a-strong-random-value")
    assert cfg.secret() == "a-strong-random-value"


def test_session_kwargs_secure_in_prod(monkeypatch):
    monkeypatch.delenv("LEADVAULT_ENV", raising=False)
    monkeypatch.delenv("LEADVAULT_SECRET", raising=False)
    assert cfg.session_kwargs()["https_only"] is False
    monkeypatch.setenv("LEADVAULT_ENV", "prod")
    monkeypatch.setenv("LEADVAULT_SECRET", "strong")
    k = cfg.session_kwargs()
    assert k["https_only"] is True and k["same_site"] == "lax"


def test_admin_credentials(monkeypatch):
    monkeypatch.delenv("LEADVAULT_ENV", raising=False)
    monkeypatch.delenv("LEADVAULT_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("LEADVAULT_ADMIN_PASSWORD", raising=False)
    assert cfg.admin_credentials() == ("admin@leadvault.local", "admin12345")  # dev default
    monkeypatch.setenv("LEADVAULT_ENV", "prod")
    assert cfg.admin_credentials() is None                                     # prod, no env -> none
    monkeypatch.setenv("LEADVAULT_ADMIN_EMAIL", "boss@acme.com")
    monkeypatch.setenv("LEADVAULT_ADMIN_PASSWORD", "rotated-secret")
    assert cfg.admin_credentials() == ("boss@acme.com", "rotated-secret")


def test_seed_demo_buyer(monkeypatch):
    monkeypatch.delenv("LEADVAULT_ENV", raising=False)
    monkeypatch.delenv("LEADVAULT_SEED_DEMO_BUYER", raising=False)
    assert cfg.seed_demo_buyer() is True                 # dev default on
    monkeypatch.setenv("LEADVAULT_ENV", "prod")
    assert cfg.seed_demo_buyer() is False                # prod default off
    monkeypatch.setenv("LEADVAULT_SEED_DEMO_BUYER", "true")
    assert cfg.seed_demo_buyer() is True                 # explicit override
