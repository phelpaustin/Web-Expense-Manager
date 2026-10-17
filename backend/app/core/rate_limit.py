import logging

from slowapi import Limiter
from starlette.requests import Request

from app.core.config import settings

log = logging.getLogger("rate_limit")
_warned_unconfigured_proxy = False


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
    return full[-(count + 1)] if len(full) > count else full[0]


# Rate limiting keyed by client IP. Applied per-endpoint via @limiter.limit(...).
limiter = Limiter(key_func=client_ip)
