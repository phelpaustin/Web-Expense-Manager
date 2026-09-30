"""Foreign-exchange rate lookups via Frankfurter (frankfurter.dev) — free, no API
key, no quota. Rates are cached in memory per base currency; if a fetch fails
(offline dev, API hiccup) we fall back to the last cached rates, or finally to
an identity rate (1.0) so a currency lookup never breaks a page.
"""
import logging
import time

import requests

log = logging.getLogger("fx")

_RATES_URL = "https://api.frankfurter.dev/v2/rates"
_CACHE_TTL_SECONDS = 12 * 60 * 60  # rates only change daily — no need to refetch often
_cache: dict[str, tuple[float, dict[str, float]]] = {}  # base -> (fetched_at, {quote: rate})


def _fetch_rates(base: str) -> dict[str, float] | None:
    try:
        resp = requests.get(_RATES_URL, params={"base": base}, timeout=5)
        resp.raise_for_status()
        return {row["quote"]: row["rate"] for row in resp.json()}
    except Exception:
        log.warning("Failed to fetch FX rates for base %s", base, exc_info=True)
        return None


def get_rates(base: str) -> dict[str, float]:
    """All known rates FROM `base` TO other currencies, e.g. {"USD": 0.095, ...}."""
    base = (base or "SEK").upper()
    cached = _cache.get(base)
    if cached and time.time() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    rates = _fetch_rates(base)
    if rates is None:
        return cached[1] if cached else {}
    _cache[base] = (time.time(), rates)
    return rates


def get_rate(from_currency: str, to_currency: str) -> float:
    """Conversion factor such that amount_in_to = amount_in_from * get_rate(from, to).
    Same-currency pairs and unknown currencies both return 1.0 (never raises)."""
    from_currency = (from_currency or "SEK").upper()
    to_currency = (to_currency or "SEK").upper()
    if from_currency == to_currency:
        return 1.0
    return get_rates(from_currency).get(to_currency, 1.0)
