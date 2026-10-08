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
# After a failed fetch, don't retry for a short while: otherwise every request
# (and every converted row) would wait out the HTTP timeout during an outage.
_FAILURE_BACKOFF_SECONDS = 60
_last_failure: dict[str, float] = {}  # base -> time of last failed fetch


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
    failed_at = _last_failure.get(base)
    if failed_at is not None and time.time() - failed_at < _FAILURE_BACKOFF_SECONDS:
        return cached[1] if cached else None
    rates = _fetch_rates(base)
    if rates is None:
        _last_failure[base] = time.time()
        return cached[1] if cached else None
    _last_failure.pop(base, None)
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


# ── Convertible-currency allow-list ───────────────────────────────────────
# The ISO 4217 list in app.core.currency includes codes (XXX, XAU, retired
# currencies, ...) that Frankfurter has no rate for. Accepting them on write
# makes every FX-dependent endpoint unusable, so writes are restricted to the
# currencies we can actually convert.
#
# The set is derived from the same /v2/rates response the converter already
# uses (base EUR + every quote), cached with the rates. If Frankfurter is
# unreachable and nothing is cached, fall back to this conservative list of
# the major ECB reference currencies so writes keep working during an outage.
_FALLBACK_CONVERTIBLE = frozenset(
    "AUD BGN BRL CAD CHF CNY CZK DKK EUR GBP HKD HUF IDR ILS INR ISK JPY KRW "
    "MXN MYR NOK NZD PHP PLN RON SEK SGD THB TRY USD ZAR".split()
)


def supported_currencies() -> frozenset[str]:
    """Currency codes we can convert (live set when available, else fallback)."""
    rates = get_rates("EUR")
    if not rates:
        return _FALLBACK_CONVERTIBLE
    return frozenset(rates) | {"EUR"}


def normalize_convertible_currency(value: str) -> str:
    """Like normalize_currency, but also requires that the currency is convertible.

    Raises ValueError (so it works inside pydantic validators) otherwise.
    """
    code = normalize_currency(value)
    if code not in supported_currencies():
        raise ValueError(
            f"Currency {code} is not supported for conversion; "
            "use a currency with a published exchange rate (e.g. EUR, USD, SEK)."
        )
    return code
