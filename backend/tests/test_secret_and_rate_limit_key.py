"""SECRET_KEY startup guard and proxy-aware rate-limit key."""
import pytest
from starlette.requests import Request

from app.core import rate_limit
from app.core.config import DEFAULT_SECRET, insecure_secret_reason, settings


@pytest.mark.parametrize(
    "secret",
    ["", "   ", DEFAULT_SECRET, "dev-secret-change-me", "change-me-generate-with-openssl-rand-hex-32",
     "your-secret-key-your-secret-key-1234", "short", "a" * 31],
)
def test_weak_or_placeholder_secrets_are_rejected(secret):
    assert insecure_secret_reason(secret)


@pytest.mark.parametrize("secret", ["a" * 32, "0123456789abcdef" * 4, "t" * 40])
def test_strong_secrets_are_accepted(secret):
    assert insecure_secret_reason(secret) is None


def test_startup_refuses_weak_secret_in_production(monkeypatch):
    import asyncio
    import main

    monkeypatch.setattr(settings, "database_url", "postgresql://u:p@localhost/db")
    monkeypatch.setattr(settings, "secret_key", "dev-secret-change-me")

    async def start():
        async with main.lifespan(main.app):
            pass

    with pytest.raises(RuntimeError, match="not safe for production"):
        asyncio.run(start())


def _request(peer, xff=None):
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234), "method": "GET", "path": "/"})


def test_ip_is_the_connection_when_no_proxy_is_trusted(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 0)
    # A spoofed header must not change the key.
    assert rate_limit.client_ip(_request("10.0.0.1", "6.6.6.6")) == "10.0.0.1"


def test_visitor_ip_is_read_from_the_trusted_proxy_chain(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    assert rate_limit.client_ip(_request("10.0.0.1", "203.0.113.7")) == "203.0.113.7"
    monkeypatch.setattr(settings, "trusted_proxy_count", 2)
    assert rate_limit.client_ip(_request("10.0.0.1", "203.0.113.7, 172.16.0.2")) == "203.0.113.7"


def test_client_supplied_entries_are_ignored(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    # The visitor sent "1.1.1.1"; the proxy appended the address it really saw.
    assert rate_limit.client_ip(_request("10.0.0.1", "1.1.1.1, 203.0.113.7")) == "203.0.113.7"


def test_short_chain_falls_back_instead_of_failing(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 3)
    assert rate_limit.client_ip(_request("10.0.0.1")) == "10.0.0.1"
    assert rate_limit.client_ip(_request("10.0.0.1", "203.0.113.7")) == "203.0.113.7"


# --- the secret check no longer depends on the database type -------------------------------------

def _start(monkeypatch, *, database_url, secret, app_env="production"):
    import asyncio
    import main

    monkeypatch.setattr(settings, "database_url", database_url)
    monkeypatch.setattr(settings, "secret_key", secret)
    monkeypatch.setattr(settings, "app_env", app_env)
    monkeypatch.setattr(main, "run_migrations", lambda: None)
    monkeypatch.setattr(main, "start_backfill", lambda: None)

    async def start():
        async with main.lifespan(main.app):
            pass

    asyncio.run(start())


@pytest.mark.parametrize("secret", [DEFAULT_SECRET, "change-me-generate-with-openssl-rand-hex-32", "short"])
def test_sqlite_refuses_a_weak_secret_by_default(monkeypatch, secret):
    with pytest.raises(RuntimeError, match="not safe for production"):
        _start(monkeypatch, database_url="sqlite:///./x.db", secret=secret)


def test_sqlite_accepts_a_strong_secret(monkeypatch):
    _start(monkeypatch, database_url="sqlite:///./x.db", secret="a" * 40)


def test_development_mode_allows_the_dev_secret_on_sqlite(monkeypatch):
    _start(monkeypatch, database_url="sqlite:///./x.db", secret=DEFAULT_SECRET, app_env="development")


def test_development_flag_is_ignored_on_postgres(monkeypatch):
    with pytest.raises(RuntimeError, match="not safe for production"):
        _start(monkeypatch, database_url="postgresql://u:p@localhost/db", secret=DEFAULT_SECRET, app_env="development")


@pytest.mark.parametrize(
    "app_env, database_url, expected",
    [
        ("production", "sqlite:///./x.db", False),
        ("", "sqlite:///./x.db", False),
        ("development", "sqlite:///./x.db", True),
        (" Development ", "sqlite:///./x.db", True),
        ("development", "postgresql://u:p@h/db", False),
    ],
)
def test_development_mode_needs_the_flag_and_sqlite(monkeypatch, app_env, database_url, expected):
    monkeypatch.setattr(settings, "app_env", app_env)
    monkeypatch.setattr(settings, "database_url", database_url)
    assert settings.development_mode is expected


# --- Docker on a Mac hides visitor addresses: say so once ----------------------------------------

def _docker_warnings(caplog):
    return [r for r in caplog.records if r.name == "rate_limit" and "Docker" in r.getMessage()]


@pytest.mark.parametrize("visitor", ["192.168.65.1", "172.17.0.1", "172.18.0.1"])
def test_docker_internal_visitor_address_logs_one_warning(monkeypatch, caplog, visitor):
    import logging

    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    monkeypatch.setattr(rate_limit, "_warned_docker_address", False)
    with caplog.at_level(logging.WARNING, logger="rate_limit"):
        assert rate_limit.client_ip(_request("172.18.0.4", visitor)) == visitor  # the address is still used
        rate_limit.client_ip(_request("172.18.0.4", visitor))  # a second request does not repeat it
    assert len(_docker_warnings(caplog)) == 1


@pytest.mark.parametrize("visitor", ["192.168.1.23", "10.0.0.7", "203.0.113.7"])
def test_real_visitor_addresses_do_not_warn(monkeypatch, caplog, visitor):
    import logging

    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    monkeypatch.setattr(rate_limit, "_warned_docker_address", False)
    with caplog.at_level(logging.WARNING, logger="rate_limit"):
        assert rate_limit.client_ip(_request("172.18.0.4", visitor)) == visitor
    assert _docker_warnings(caplog) == []


def test_no_docker_warning_when_no_proxy_is_trusted(monkeypatch, caplog):
    import logging

    # With TRUSTED_PROXY_COUNT=0 the "visitor" is the connection itself; that case has its own warning.
    monkeypatch.setattr(settings, "trusted_proxy_count", 0)
    monkeypatch.setattr(rate_limit, "_warned_docker_address", False)
    with caplog.at_level(logging.WARNING, logger="rate_limit"):
        assert rate_limit.client_ip(_request("172.18.0.4")) == "172.18.0.4"
    assert _docker_warnings(caplog) == []
