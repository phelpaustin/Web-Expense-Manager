import ipaddress
import logging

from slowapi import Limiter
from starlette.requests import Request

from app.core.config import settings

log = logging.getLogger("rate_limit")
_warned_unconfigured_proxy = False
_warned_docker_address = False

# Address ranges Docker uses internally: its bridge networks (172.16.0.0/12) and the VM that Docker
# Desktop for Mac runs in (192.168.65.0/24).
_DOCKER_NETWORKS = (ipaddress.ip_network("172.16.0.0/12"), ipaddress.ip_network("192.168.65.0/24"))


def _note_docker_address(ip: str) -> None:
    """Say once, in the log, when the visitor's address looks like one of Docker's own.

    Docker on a Mac (Docker Desktop, some Colima setups) replaces every device's address with an
    internal one before the request reaches the website container. Then all visitors share one rate
    limit and the sign-in history shows the same address for everyone. Code cannot undo that, so the
    warning points at the README. It is only a hint: a home network that really uses these ranges
    triggers it too, and can ignore it.
    """
    global _warned_docker_address
    if _warned_docker_address:
        return
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return
    if any(address in network for network in _DOCKER_NETWORKS):
        _warned_docker_address = True
        log.warning(
            "A visitor address (%s) looks like one of Docker's internal addresses. If your devices are not "
            "on that network, Docker is hiding their real addresses: all visitors then share one rate limit "
            "and Sign-in activity shows the same address for everyone. See deploy/onprem/README.md, "
            "'Seeing real visitor addresses'.",
            ip,
        )


def client_ip(request: Request) -> str:
    """The visitor's IP, for rate limiting.

    Behind a reverse proxy (Render, a CDN) the connection address is the proxy's, so
    every visitor would share one limit. With TRUSTED_PROXY_COUNT = N, the visitor is
    the address the outermost trusted proxy saw: counting N proxies back from the
    connection. Entries further left in X-Forwarded-For are client-supplied and are
    never trusted. With N = 0 the header is ignored entirely.
    """
    global _warned_unconfigured_proxy
    peer = request.client.host if request.client else "unknown"
    header = request.headers.get("x-forwarded-for", "")
    chain = [p.strip() for p in header.split(",") if p.strip()]
    count = settings.trusted_proxy_count
    if count == 0:
        if chain and not _warned_unconfigured_proxy:
            _warned_unconfigured_proxy = True
            log.warning(
                "Requests carry X-Forwarded-For (%d entries) but TRUSTED_PROXY_COUNT is 0, so rate "
                "limits are per proxy, not per visitor. If this app is behind a proxy, set "
                "TRUSTED_PROXY_COUNT to the number of proxies in front of it (see the README).",
                len(chain),
            )
        return peer
    full = chain + [peer]  # the last entry is the nearest proxy (the connection itself)
    visitor = full[-(count + 1)] if len(full) > count else full[0]
    _note_docker_address(visitor)
    return visitor


# Rate limiting keyed by client IP. Applied per-endpoint via @limiter.limit(...).
limiter = Limiter(key_func=client_ip)


# Limit strings are read at request time (callables), so env overrides and tests can change them.
def login_limit() -> str:
    return settings.rate_limit_login


def register_limit() -> str:
    return settings.rate_limit_register


def google_limit() -> str:
    return settings.rate_limit_google


def sensitive_limit() -> str:
    return settings.rate_limit_sensitive


def import_limit() -> str:
    return settings.rate_limit_import


def import_ai_limit() -> str:
    return settings.rate_limit_import_ai
