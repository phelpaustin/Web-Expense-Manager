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
