"""How does a month compare with last month, the same month a year ago and your usual?

"September: 9,200 SEK, up 4% on August, down 8% on September last year, and 12% above your
3-month average." Pure functions on plain dicts.

The month still in progress is compared like for like: its days so far against the same
days of each earlier month, since a part month set against a whole one would always look
like a fall. The average is the mean of the (up to) 3 months before the chosen one, taken
over the same days.

A comparison is only offered when there is history to compare with: a month before your
first expense is "not enough history", not a spend of zero.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.money import as_decimal, quantize_money
from app.logic.analytics import current_month_key
from app.logic.category_change import (
    _as_date,
    _direction,
    _month_key,
    _pct,
    default_month,
    months_with_spend,
    previous_month,
)

AVERAGE_MONTHS = 3
ZERO = quantize_money(0)


def same_month_last_year(month: str) -> str:
    return f"{int(month[:4]) - 1:04d}{month[4:]}"


def _total(expenses: list[dict], month: str, through_day: int | None) -> Decimal:
    total = Decimal(0)
    for e in expenses:
        d = _as_date(e.get("date"))
        if d is None or _month_key(d) != month:
            continue
        if through_day is not None and d.day > through_day:
            continue
        total += as_decimal(e.get("amount"))
    return quantize_money(total)


def _row(key: str, label: str, now: Decimal, before: Decimal | None, **extra) -> dict:
    if before is None:
        return {"key": key, "label": label, "available": False, "before": None, "change": None,
                "pct_change": None, "direction": None, **extra}
    change = now - before
    return {"key": key, "label": label, "available": True, "before": before, "change": change,
            "pct_change": _pct(change, before), "direction": _direction(change), **extra}


def period_compare(expenses: list[dict], month: str, today: date | None = None) -> dict:
    today = today or date.today()
    in_progress = month == current_month_key(today)
    through_day = today.day if in_progress else None
    first = (months_with_spend(expenses) or [month])[0]

    now = _total(expenses, month, through_day)

    last_month = previous_month(month)
    last_year = same_month_last_year(month)
    usual = []
    cursor = month
    for _ in range(AVERAGE_MONTHS):
        cursor = previous_month(cursor)
        if cursor >= first:
            usual.append(cursor)

    average = (quantize_money(sum((_total(expenses, m, through_day) for m in usual), Decimal(0)) / len(usual))
               if usual else None)

    return {
        "month": month,
        "partial": in_progress,
        "through_day": through_day,
        "total": now,
        "comparisons": [
            _row("last_month", "Against last month", now,
                 _total(expenses, last_month, through_day) if last_month >= first else None, month=last_month),
            _row("last_year", "Against last year", now,
                 _total(expenses, last_year, through_day) if last_year >= first else None, month=last_year),
            _row("average", f"Against {AVERAGE_MONTHS}-month average", now, average, months=usual),
        ],
        # Every month with spending (and the one asked for), newest first, for the month picker.
        "months": sorted(set(months_with_spend(expenses)) | {month}, reverse=True),
    }


__all__ = ["period_compare", "default_month", "same_month_last_year"]
