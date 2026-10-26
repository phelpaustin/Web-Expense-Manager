"""Biggest movers: which categories and shops rose most, fell most, or are new this month.

A month is set against the month before it, by category and by shop. Three short lists for each:

- rose: spent more than the month before (and spent something before), biggest rise first
- fell: spent less than the month before, biggest fall first (a shop or category with nothing
  this month is the biggest fall it can have, and is marked "stopped")
- new: nothing the month before, something now, biggest first

The month still in progress is compared like for like: its days so far against the same
days of the month before, since a part month set against a whole one would always look
like a fall. Pure functions on plain dicts.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.money import as_decimal, quantize_money
from app.logic.analytics import current_month_key
from app.logic.category_change import (
    UNCATEGORISED,
    _as_date,
    _month_key,
    _pct,
    _status,
    default_month,
    months_with_spend,
    previous_month,
)

DEFAULT_TOP = 3
ZERO = quantize_money(0)


def _category(e: dict) -> str:
    return str(e.get("category") or "").strip() or UNCATEGORISED


def _shop(e: dict) -> str:
    return str(e.get("shop") or "").strip()


def _totals(expenses: list[dict], month: str, through_day: int | None, name_of) -> dict[str, Decimal]:
    sums: dict[str, Decimal] = {}
    for e in expenses:
        d = _as_date(e.get("date"))
        if d is None or _month_key(d) != month:
            continue
        if through_day is not None and d.day > through_day:
            continue
        name = name_of(e)
        if not name:
            continue  # an expense with no shop belongs to no shop
        sums[name] = sums.get(name, Decimal(0)) + as_decimal(e.get("amount"))
    return {n: quantize_money(v) for n, v in sums.items()}


def _lists(now_by: dict[str, Decimal], before_by: dict[str, Decimal], top: int) -> dict:
    rows = []
    for name in set(now_by) | set(before_by):
        now, before = now_by.get(name, ZERO), before_by.get(name, ZERO)
        change = now - before
        rows.append({"name": name, "now": now, "before": before, "change": change,
                     "pct_change": _pct(change, before), "status": _status(now, before)})
    rose = sorted((r for r in rows if r["change"] > 0 and r["before"] > 0), key=lambda r: (-r["change"], r["name"]))
    fell = sorted((r for r in rows if r["change"] < 0), key=lambda r: (r["change"], r["name"]))
    new = sorted((r for r in rows if r["status"] == "new"), key=lambda r: (-r["now"], r["name"]))
    return {"rose": rose[:top], "fell": fell[:top], "new": new[:top]}


def movers(expenses: list[dict], month: str, today: date | None = None, top: int = DEFAULT_TOP) -> dict:
    today = today or date.today()
    in_progress = month == current_month_key(today)
    through_day = today.day if in_progress else None
    before_month = previous_month(month)

    def both(name_of):
        return _lists(_totals(expenses, month, through_day, name_of),
                      _totals(expenses, before_month, through_day, name_of), top)

    categories, shops = both(_category), both(_shop)
    first = (months_with_spend(expenses) or [month])[0]
    return {
        "month": month,
        "compare_month": before_month,
        "partial": in_progress,
        "through_day": through_day,
        # Nothing before the month to set it against: a first month is not "all new".
        "available": first < month,
        "categories": categories,
        "shops": shops,
        "months": sorted(set(months_with_spend(expenses)) | {month}, reverse=True),
    }


__all__ = ["movers", "default_month"]
