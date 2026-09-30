"""Convert expense amounts into one common base currency for aggregation.

Per-expense `amount`/`currency` are never mutated in the database or on the
paginated expenses list — this only produces a *derived* view for
analytics/budgets/metrics/alerts, which need one common unit to sum and
compare across currencies (previously they summed raw amounts regardless of
currency, which is wrong whenever a user has expenses in more than one).
"""
from __future__ import annotations

from typing import Callable


def convert_expenses(
    expenses: list[dict], base_currency: str, get_rate: Callable[[str, str], float]
) -> list[dict]:
    base_currency = (base_currency or "SEK").upper()
    converted = []
    for e in expenses:
        currency = (e.get("currency") or base_currency).upper()
        rate = get_rate(currency, base_currency)
        out = dict(e)
        out["original_amount"] = e["amount"]
        out["original_currency"] = currency
        out["amount"] = round(e["amount"] * rate, 2)
        out["currency"] = base_currency
        converted.append(out)
    return converted
