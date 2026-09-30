"""Foreign-exchange rate lookups via Frankfurter (frankfurter.dev)."""
from decimal import Decimal
import logging
import time

import requests

from app.core.currency import normalize_currency

log = logging.getLogger("fx")

_RATES_URL = "https://api.frankfurter.dev/v2/rates"
_CACHE_TTL_SECONDS = 12 * 60 * 60  # rates only change daily — no need to refetch often
_cache: dict[str, tuple[float, dict[str, Decimal]]] = {}  # base -> (fetched_at, {quote: rate})


def _fetch_rates(base: str) -> dict[str, Decimal] | None:
    try:
        resp = requests.get(_RATES_URL, params={"base": base}, timeout=5)
        resp.raise_for_status()
        return {row["quote"].upper(): Decimal(str(row["rate"])) for row in resp.json()}
    except Exception:
        log.warning("Failed to fetch FX rates for base %s", base, exc_info=True)
        return None


def get_rates(base: str) -> dict[str, Decimal] | None:
    """All known rates FROM `base` TO other currencies, e.g. {"USD": 0.095, ...}."""
    base = normalize_currency(base or "SEK")
    cached = _cache.get(base)
    if cached and time.time() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    rates = _fetch_rates(base)
    if rates is None:
        return cached[1] if cached else None
    _cache[base] = (time.time(), rates)
    return rates


def get_rate(from_currency: str, to_currency: str) -> Decimal | None:
    """Conversion factor such that amount_in_to = amount_in_from * get_rate(from, to).
    Same-currency pairs return 1.0. Unknown or unavailable conversions return None.
    """
    from_currency = normalize_currency(from_currency or "SEK")
    to_currency = normalize_currency(to_currency or "SEK")
    if from_currency == to_currency:
        return Decimal("1")
    rates = get_rates(from_currency)
    return rates.get(to_currency) if rates is not None else None
