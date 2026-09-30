"""Convert expense amounts into one common base currency for aggregation.

Per-expense `amount`/`currency` are never mutated in the database or on the
paginated expenses list — this only produces a *derived* view for
analytics/budgets/metrics/alerts, which need one common unit to sum and
compare across currencies (previously they summed raw amounts regardless of
currency, which is wrong whenever a user has expenses in more than one).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable

from app.core.currency import normalize_currency


class CurrencyConversionUnavailable(ValueError):
    pass


def convert_expenses(
    expenses: list[dict], base_currency: str, get_rate: Callable[[str, str], Decimal | None]
) -> list[dict]:
    try:
        base_currency = normalize_currency(base_currency or "SEK")
    except ValueError as exc:
        raise CurrencyConversionUnavailable(str(exc)) from exc
    converted = []
    for e in expenses:
        try:
            currency = normalize_currency(e.get("currency") or base_currency)
        except ValueError as exc:
            raise CurrencyConversionUnavailable(str(exc)) from exc
        rate = get_rate(currency, base_currency)
        if rate is None:
            raise CurrencyConversionUnavailable(
                f"FX conversion unavailable for {currency} -> {base_currency}"
            )
        out = dict(e)
        out["original_amount"] = e["amount"]
        out["original_currency"] = currency
        out["amount"] = (Decimal(str(e["amount"])) * rate).quantize(Decimal("0.01"))
        out["currency"] = base_currency
        converted.append(out)
    return converted
