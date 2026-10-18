"""Convert expense amounts into one common base currency for aggregation.

Per-expense `amount`/`currency` are never mutated in the database or on the
paginated expenses list — this only produces a *derived* view for
analytics/budgets/metrics/alerts, which need one common unit to sum and
compare across currencies (previously they summed raw amounts regardless of
currency, which is wrong whenever a user has expenses in more than one).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable  # get_rate(from, to, on_date) -> Decimal | None

from app.core.currency import normalize_currency


class CurrencyConversionUnavailable(ValueError):
    pass


_MISSING = object()
_CENT = Decimal("0.01")
_PRECISE = Decimal("0.0001")


def _convert_row(e: dict, currency: str, base_currency: str, rate: Decimal) -> dict:
    out = dict(e)
    amount = e["amount"]
    out["original_amount"] = amount
    out["original_currency"] = currency
    out["amount"] = ((amount if isinstance(amount, Decimal) else Decimal(str(amount))) * rate).quantize(_CENT)
    unit_price = e.get("price_per_unit")
    if unit_price is not None:
        out["original_price_per_unit"] = unit_price
        out["price_per_unit"] = (
            (unit_price if isinstance(unit_price, Decimal) else Decimal(str(unit_price))) * rate
        ).quantize(_PRECISE)
    out["currency"] = base_currency
    return out


def convert_expenses(
    expenses: list[dict], base_currency: str, get_rate: Callable[[str, str], Decimal | None]
) -> list[dict]:
    try:
        base_currency = normalize_currency(base_currency or "SEK")
    except ValueError as exc:
        raise CurrencyConversionUnavailable(str(exc)) from exc
    # Many rows share a currency and a day, so each (currency, day) rate is looked up once.
    rates: dict = {}
    codes: dict = {}
    converted = []
    for e in expenses:
        raw = e.get("currency") or base_currency
        currency = codes.get(raw)
        if currency is None:
            try:
                currency = codes[raw] = normalize_currency(raw)
            except ValueError as exc:
                raise CurrencyConversionUnavailable(str(exc)) from exc
        key = (currency, e.get("date"))
        rate = rates.get(key, _MISSING)
        if rate is _MISSING:
            rate = rates[key] = get_rate(currency, base_currency, e.get("date"))
        if rate is None:
            raise CurrencyConversionUnavailable(
                f"FX conversion unavailable for {currency} -> {base_currency}"
            )
        converted.append(_convert_row(e, currency, base_currency, rate))
    return converted


def partition_convertible(
    expenses: list[dict], target_currency: str, get_rate: Callable[..., Decimal | None]
) -> tuple[list[dict], list[dict]]:
    """Split expenses into (convertible, unconvertible) for ``target_currency``.

    Unconvertible = no exchange rate for the expense's currency (unknown code,
    unsupported by the provider, or not loadable right now).
    """
    try:
        target = normalize_currency(target_currency or "SEK")
    except ValueError as exc:
        raise CurrencyConversionUnavailable(str(exc)) from exc
    ok: list[dict] = []
    bad: list[dict] = []
    for e in expenses:
        try:
            currency = normalize_currency(e.get("currency") or target)
        except ValueError:
            bad.append(e)
            continue
        (ok if get_rate(currency, target, e.get("date")) is not None else bad).append(e)
    return ok, bad


def convert_expenses_partial(
    expenses: list[dict], base_currency: str, get_rate: Callable[..., Decimal | None]
) -> tuple[list[dict], int]:
    """Convert what can be converted; skip rows whose currency has no rate.

    Returns (converted_rows, skipped_count). Unlike convert_expenses, a single
    unconvertible expense never prevents the rest from being aggregated.
    An invalid *target* currency is still an error: nothing can be converted.
    One pass, one rate lookup per distinct (currency, day).
    """
    try:
        target = normalize_currency(base_currency or "SEK")
    except ValueError as exc:
        raise CurrencyConversionUnavailable(str(exc)) from exc
    rates: dict = {}
    codes: dict = {}
    converted: list[dict] = []
    skipped = 0
    for e in expenses:
        raw = e.get("currency") or target
        currency = codes.get(raw)
        if currency is None:
            try:
                currency = codes[raw] = normalize_currency(raw)
            except ValueError:
                skipped += 1
                continue
        key = (currency, e.get("date"))
        rate = rates.get(key, _MISSING)
        if rate is _MISSING:
            rate = rates[key] = get_rate(currency, target, e.get("date"))
        if rate is None:
            skipped += 1
            continue
        converted.append(_convert_row(e, currency, target, rate))
    return converted, skipped
