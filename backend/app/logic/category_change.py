"""Why did spending change between two months? Attribute the change to categories.

"Spending is up 1,200 SEK vs last month: groceries +800, dining +300." Each category's
change is its spend this month minus its spend in the month before, so the category
changes always add up to the total change exactly (everything is rounded per category
first, and the totals are the sums of those rounded figures).

The month still in progress is compared like for like: its days so far against the same
days of the month before, since a part month set against a whole one would always look
like a fall.
"""
from __future__ import annotations

import datetime
from datetime import date
from decimal import Decimal

import pandas as pd

from app.core.money import as_decimal, quantize_money
from app.logic.analytics import complete_months, current_month_key

UNCATEGORISED = "Uncategorised"
DEFAULT_TOP = 8
ZERO = quantize_money(0)


def _as_date(value) -> date | None:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def previous_month(month: str) -> str:
    return str(pd.Period(month, freq="M") - 1)


def months_with_spend(expenses: list[dict]) -> list[str]:
    """Every calendar month that has at least one expense, oldest first."""
    found = set()
    for e in expenses:
        d = _as_date(e.get("date"))
        if d is not None:
            found.add(_month_key(d))
    return sorted(found)


def default_month(expenses: list[dict], today: date | None = None) -> str:
    """The month to explain when none is chosen.

    The last finished month, so the answer matches the "vs previous month" figure on the
    dashboard; the month in progress only when nothing has finished yet.
    """
    totals: dict[str, Decimal] = {}
    for e in expenses:
        d = _as_date(e.get("date"))
        if d is not None:
            totals[_month_key(d)] = totals.get(_month_key(d), Decimal(0)) + as_decimal(e.get("amount"))
    monthly = [{"month": m, "total": quantize_money(t)} for m, t in sorted(totals.items())]
    done = complete_months(monthly, today)
    return done[-1]["month"] if done else current_month_key(today)


def _totals_by_category(expenses: list[dict], month: str, through_day: int | None) -> dict[str, Decimal]:
    sums: dict[str, Decimal] = {}
    for e in expenses:
        d = _as_date(e.get("date"))
        if d is None or _month_key(d) != month:
            continue
        if through_day is not None and d.day > through_day:
            continue
        category = str(e.get("category") or "").strip() or UNCATEGORISED
        sums[category] = sums.get(category, Decimal(0)) + as_decimal(e.get("amount"))
    return {c: quantize_money(v) for c, v in sums.items()}


def _pct(change: Decimal, before: Decimal) -> float | None:
    """Percent change, or None when there was nothing before to compare with."""
    return round(float(change / before * 100), 1) if before else None


def _direction(change: Decimal) -> str:
    return "up" if change > 0 else "down" if change < 0 else "flat"


def _status(now: Decimal, before: Decimal) -> str:
    if before == 0 and now > 0:
        return "new"
    if now == 0 and before > 0:
        return "stopped"
    return "unchanged" if now == before else "changed"


def category_change(expenses: list[dict], month: str, today: date | None = None, top: int = DEFAULT_TOP) -> dict:
    """Break the change in total spend from the month before `month` down by category.

    `categories` holds the `top` biggest movers (by size, up or down); `other` rolls the
    remaining movers into one line, so the two always add up to the total change.
    Categories that did not change are left out and only counted.
    """
    today = today or date.today()
    before_month = previous_month(month)
    in_progress = month == current_month_key(today)
    through_day = today.day if in_progress else None

    now_by = _totals_by_category(expenses, month, through_day)
    before_by = _totals_by_category(expenses, before_month, through_day)

    rows = []
    for category in set(now_by) | set(before_by):
        now, before = now_by.get(category, ZERO), before_by.get(category, ZERO)
        change = now - before
        rows.append({
            "category": category,
            "now": now,
            "before": before,
            "change": change,
            "pct_change": _pct(change, before),
            "status": _status(now, before),
        })

    total_now = sum((r["now"] for r in rows), ZERO)
    total_before = sum((r["before"] for r in rows), ZERO)
    total_change = total_now - total_before

    moved = sorted((r for r in rows if r["change"] != 0), key=lambda r: (-abs(r["change"]), r["category"]))
    shown, rest = moved[:top], moved[top:]
    other = None
    if rest:
        other_now = sum((r["now"] for r in rest), ZERO)
        other_before = sum((r["before"] for r in rest), ZERO)
        other = {
            "count": len(rest),
            "now": other_now,
            "before": other_before,
            "change": other_now - other_before,
        }

    return {
        "month": month,
        "compare_month": before_month,
        "partial": in_progress,
        "through_day": through_day,
        "available": bool(rows),
        "total": {
            "now": total_now,
            "before": total_before,
            "change": total_change,
            "pct_change": _pct(total_change, total_before),
            "direction": _direction(total_change),
        },
        "categories": shown,
        "other": other,
        "unchanged_count": sum(1 for r in rows if r["change"] == 0),
        "months": months_with_spend(expenses),
    }
