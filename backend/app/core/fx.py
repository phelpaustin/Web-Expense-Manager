"""Foreign-exchange rate lookups via Frankfurter (frankfurter.dev)."""
import datetime as dt
from collections import defaultdict
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


def get_rate(from_currency: str, to_currency: str, on: "dt.date | str | None" = None) -> Decimal | None:
    """Conversion factor such that amount_in_to = amount_in_from * get_rate(from, to, on).

    With ``on`` (an expense date) the rate is the historical rate for that day,
    read from the cache that ``ensure_rates`` fills. Without it, or when the
    historical rate isn't available (e.g. provider outage and not yet cached),
    it falls back to the latest rate. Same-currency pairs return 1; unknown or
    unavailable conversions return None.
    """
    from_currency = normalize_currency(from_currency or "SEK")
    to_currency = normalize_currency(to_currency or "SEK")
    if from_currency == to_currency:
        return Decimal("1")
    if on is not None:
        day = _as_date(on)
        if day is not None:
            r_from = _eur_rate(day, from_currency)
            r_to = _eur_rate(day, to_currency)
            if r_from and r_to:
                return r_to / r_from
    rates = get_rates(from_currency)
    return rates.get(to_currency) if rates is not None else None


# ── Historical (expense-date) rates ───────────────────────────────────────
# Frankfurter's historical rates are immutable, so final rates are cached
# forever: in memory for speed and in the `fx_rates` table so they survive
# restarts and are shared between workers. Only EUR-based rates are stored
# (units of currency per 1 EUR); cross rates are derived from two of them.
#
# Frankfurter publishes business days only. Each calendar day gets the rate of
# the latest published day on or before it, so a Saturday expense uses
# Friday's rate. Days after the last published day (today, weekends not yet
# followed by a published business day, future dates) are *provisional*: they
# are kept in memory with a short TTL and never persisted, because the provider
# may still publish or revise them.
_FINAL: dict[tuple[dt.date, str], Decimal] = {}
_PROVISIONAL: dict[tuple[dt.date, str], tuple[float, Decimal]] = {}
_NO_DATA: dict[str, float] = {}  # currency -> when the provider last had no data for it

_SERIES_CHUNK_DAYS = 90        # request windows stay small so the API never downsamples
_MAX_CHUNKS_PER_CALL = 6       # bound the work one request can trigger; the rest fills in later
_SEED_DAYS = 7                 # look this far back so weekends/holidays have a prior rate
_PROVISIONAL_TTL_SECONDS = 60 * 60
_NO_DATA_TTL_SECONDS = 60 * 60
_SERIES_BACKOFF_KEY = "__series__"


def _utc_today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def _as_date(value) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _eur_rate(day: dt.date, currency: str) -> Decimal | None:
    if currency == "EUR":
        return Decimal("1")
    day = min(day, _utc_today())
    final = _FINAL.get((day, currency))
    if final is not None:
        return final
    prov = _PROVISIONAL.get((day, currency))
    if prov is not None and time.time() - prov[0] < _PROVISIONAL_TTL_SECONDS:
        return prov[1]
    return None


def _fetch_series(currencies: set[str], start: dt.date, end: dt.date) -> dict[str, dict[dt.date, Decimal]] | None:
    """EUR-based daily rates for ``currencies`` over [start, end]; None on failure."""
    try:
        resp = requests.get(
            _RATES_URL,
            params={
                "base": "EUR",
                "quotes": ",".join(sorted(currencies)),
                "from": start.isoformat(),
                "to": end.isoformat(),
            },
            timeout=10,
        )
        resp.raise_for_status()
        out: dict[str, dict[dt.date, Decimal]] = defaultdict(dict)
        for row in resp.json():
            out[row["quote"].upper()][dt.date.fromisoformat(row["date"])] = Decimal(str(row["rate"]))
        return dict(out)
    except Exception:
        log.warning("Failed to fetch FX series %s..%s for %s", start, end, sorted(currencies), exc_info=True)
        return None


def _load_stored(needed: set[tuple[dt.date, str]]) -> None:
    """Fill the in-memory cache from the fx_rates table."""
    from app.db.database import SessionLocal
    from app.db import models

    currencies = {c for _, c in needed}
    lo, hi = min(d for d, _ in needed), max(d for d, _ in needed)
    db = SessionLocal()
    try:
        rows = (
            db.query(models.FxRate)
            .filter(
                models.FxRate.currency.in_(currencies),
                models.FxRate.rate_date >= lo,
                models.FxRate.rate_date <= hi,
            )
            .all()
        )
        for r in rows:
            _FINAL[(r.rate_date, r.currency)] = Decimal(str(r.rate))
    except Exception:
        log.warning("Could not read stored FX rates", exc_info=True)
    finally:
        db.close()


def _store(rows: dict[tuple[dt.date, str], Decimal]) -> None:
    """Persist final rates. Best effort: the in-memory cache already has them."""
    if not rows:
        return
    from app.db.database import SessionLocal
    from app.db import models

    currencies = {c for _, c in rows}
    lo, hi = min(d for d, _ in rows), max(d for d, _ in rows)
    db = SessionLocal()
    try:
        existing = {
            (r.rate_date, r.currency)
            for r in db.query(models.FxRate.rate_date, models.FxRate.currency).filter(
                models.FxRate.currency.in_(currencies),
                models.FxRate.rate_date >= lo,
                models.FxRate.rate_date <= hi,
            )
        }
        db.add_all(
            models.FxRate(rate_date=d, currency=c, rate=rate)
            for (d, c), rate in rows.items()
            if (d, c) not in existing
        )
        db.commit()
    except Exception:
        db.rollback()  # e.g. another worker stored the same rows first
        log.warning("Could not store FX rates", exc_info=True)
    finally:
        db.close()


def _fill_window(
    series: dict[str, dict[dt.date, Decimal]], currencies: set[str], start: dt.date, end: dt.date
) -> dict[tuple[dt.date, str], Decimal]:
    """Turn business-day data into per-calendar-day rates for [start, end].

    Updates the in-memory caches and returns the final rows to persist.
    """
    final_rows: dict[tuple[dt.date, str], Decimal] = {}
    now = time.time()
    for cur in currencies:
        points = series.get(cur)
        if not points:
            _NO_DATA[cur] = now
            continue
        published = sorted(points)
        last_published = published[-1]
        idx = 0
        current: Decimal | None = None
        day = published[0] if published[0] > start else start
        while day <= end:
            while idx < len(published) and published[idx] <= day:
                current = points[published[idx]]
                idx += 1
            if current is not None:
                if day <= last_published:
                    final_rows[(day, cur)] = current
                    _FINAL[(day, cur)] = current
                else:
                    _PROVISIONAL[(day, cur)] = (now, current)
            day += dt.timedelta(days=1)
    return final_rows


def ensure_rates(pairs) -> None:
    """Make sure historical rates for (date, currency) pairs are cached.

    Reads the fx_rates table first, then fetches only what's missing from
    Frankfurter (newest dates first, in bounded chunks). Never raises: if rates
    can't be loaded, ``get_rate`` falls back to the latest rate.
    """
    today = _utc_today()
    now = time.time()
    needed: set[tuple[dt.date, str]] = set()
    for day, cur in pairs:
        day = _as_date(day)
        if day is None or not cur:
            continue
        cur = cur.upper()
        if cur == "EUR":
            continue
        day = min(day, today)
        if _eur_rate(day, cur) is None:
            needed.add((day, cur))
    if not needed:
        return

    _load_stored(needed)
    needed = {p for p in needed if _eur_rate(*p) is None}
    # Skip currencies the provider recently had no data for.
    needed = {(d, c) for d, c in needed if now - _NO_DATA.get(c, 0.0) >= _NO_DATA_TTL_SECONDS}
    if not needed:
        return
    failed_at = _last_failure.get(_SERIES_BACKOFF_KEY)
    if failed_at is not None and now - failed_at < _FAILURE_BACKOFF_SECONDS:
        return

    # Newest-first windows of _SERIES_CHUNK_DAYS; only windows that contain a needed date.
    newest = max(d for d, _ in needed)
    windows: dict[int, set[tuple[dt.date, str]]] = defaultdict(set)
    for d, c in needed:
        windows[(newest - d).days // _SERIES_CHUNK_DAYS].add((d, c))

    for n in sorted(windows)[:_MAX_CHUNKS_PER_CALL]:
        w_end = newest - dt.timedelta(days=n * _SERIES_CHUNK_DAYS)
        w_start = w_end - dt.timedelta(days=_SERIES_CHUNK_DAYS - 1)
        currencies = {c for _, c in windows[n]}
        # Fetch a little past the window so a weekend at its edge sees the next
        # published business day and is recognised as final rather than provisional.
        fetch_end = min(w_end + dt.timedelta(days=_SEED_DAYS), today)
        series = _fetch_series(currencies, w_start - dt.timedelta(days=_SEED_DAYS), fetch_end)
        if series is None:
            _last_failure[_SERIES_BACKOFF_KEY] = time.time()
            return
        _last_failure.pop(_SERIES_BACKOFF_KEY, None)
        _store(_fill_window(series, currencies, w_start, w_end))


def ensure_rates_for(rows, base_currency: str) -> None:
    """Prefetch the rates needed to convert ``rows`` (dicts with date/currency) into base_currency."""
    base = normalize_currency(base_currency or "SEK")
    pairs = set()
    for r in rows:
        day = r.get("date")
        if day is None:
            continue
        pairs.add((day, base))
        pairs.add((day, (r.get("currency") or base)))
    ensure_rates(pairs)


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
