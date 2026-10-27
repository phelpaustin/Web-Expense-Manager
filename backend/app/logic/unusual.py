"""Spending worth a second look: expenses far bigger than usual, and entries that may be doubled.

Unusual: a recent expense that is at least `factor` times the usual (median) expense in its
category AND above the top of that category's normal range (the upper Tukey fence, Q3 + 1.5 x IQR).
Needing both keeps a naturally wide category from flagging everything, and a tight one from
flagging a small step up. A category needs `min_history` other expenses in the last `history_months`
months before anything in it is judged, so a new category is never "unusual". Payments posted by a
recurring template are expected, so they are never flagged.

Possible duplicates: two or more entries with the same date, amount, description and shop. Lines
that belong to one receipt are one entry (the same item twice on one receipt is not a mistake). Only
a real receipt counts: expenses typed in by hand are filed under derived bills too, but those group
unrelated entries, so the caller says which bills are receipts (`receipt_bills`).

Pure functions on plain dicts.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from app.core.money import as_decimal, quantize_money
from app.logic.names import clean_name, name_key
from app.logic.price_tracker import _as_day, _months_ago_start

DEFAULT_RECENT_DAYS = 30
DEFAULT_DUPLICATE_DAYS = 60
DEFAULT_FACTOR = 3.0
DEFAULT_MIN_HISTORY = 8
DEFAULT_HISTORY_MONTHS = 12
UNCATEGORISED = "Uncategorised"


def _category(e: dict) -> str:
    return clean_name(e.get("category")) or UNCATEGORISED


def _quartiles(values: list[Decimal]) -> tuple[Decimal, Decimal]:
    """Q1 and Q3 by the median-of-halves method (the middle value is left out of both halves)."""
    ordered = sorted(values)
    half = len(ordered) // 2
    lower, upper = ordered[:half], ordered[half + (len(ordered) % 2):]
    return Decimal(str(median(lower))), Decimal(str(median(upper)))


def unusual_expenses(
    expenses: list[dict],
    today: date | None = None,
    recent_days: int = DEFAULT_RECENT_DAYS,
    factor: float = DEFAULT_FACTOR,
    min_history: int = DEFAULT_MIN_HISTORY,
    history_months: int = DEFAULT_HISTORY_MONTHS,
    top: int = 10,
) -> dict:
    today = today or date.today()
    window_start = today - timedelta(days=recent_days)
    history_start = _months_ago_start(today, history_months) if history_months > 0 else None

    by_category: dict[str, list[tuple[date, dict, Decimal]]] = defaultdict(list)
    for e in expenses:
        day = _as_day(e.get("date"))
        if day is None or day > today or (history_start is not None and day < history_start):
            continue
        by_category[name_key(_category(e))].append((day, e, as_decimal(e.get("amount"))))

    found, checked = [], 0
    for rows in by_category.values():
        for day, e, amount in rows:
            if day < window_start or e.get("recurring_template_id") is not None or amount <= 0:
                continue
            others = [a for _, o, a in rows if o is not e and a > 0]
            if len(others) < min_history:
                continue
            checked += 1
            usual = Decimal(str(median(others)))
            q1, q3 = _quartiles(others)
            fence = q3 + Decimal("1.5") * (q3 - q1)
            if usual <= 0 or amount < usual * Decimal(str(factor)) or amount <= fence:
                continue
            found.append({
                "id": e.get("id"),
                "date": day.isoformat(),
                "category": _category(e),
                "description": clean_name(e.get("description")),
                "shop": clean_name(e.get("shop")),
                "amount": quantize_money(amount),
                "usual": quantize_money(usual),
                "ratio": round(float(amount / usual), 1),
                "compared_with": len(others),
            })

    found.sort(key=lambda i: (-i["ratio"], i["date"], i["id"] or 0))
    return {"recent_days": recent_days, "checked": checked, "items": found[:top], "total_found": len(found)}


def possible_duplicates(
    expenses: list[dict],
    today: date | None = None,
    recent_days: int = DEFAULT_DUPLICATE_DAYS,
    top: int = 10,
    receipt_bills: Callable[[set], set] | None = None,
) -> dict:
    """`receipt_bills` takes the bill ids found on lookalike entries and returns those that are real
    receipts. Without it every bill counts as a receipt."""
    today = today or date.today()
    window_start = today - timedelta(days=recent_days)

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for e in expenses:
        day = _as_day(e.get("date"))
        if day is None or day > today or day < window_start:
            continue
        description, shop = name_key(e.get("description")), name_key(e.get("shop"))
        if not description and not shop:
            continue  # nothing to tell two entries apart by except the amount
        groups[(day, quantize_money(as_decimal(e.get("amount"))), description, shop, name_key(_category(e)))].append(e)

    lookalikes = {k: rows for k, rows in groups.items() if len(rows) > 1}
    bill_ids = {r["source_bill_id"] for rows in lookalikes.values() for r in rows if r.get("source_bill_id") is not None}
    receipts = (receipt_bills(bill_ids) if receipt_bills is not None else bill_ids) if bill_ids else set()

    found = []
    for (day, amount, _d, _s, _c), rows in lookalikes.items():
        # Lines of one receipt are one entry; every other entry stands alone.
        entries = {("bill", r["source_bill_id"]) if r.get("source_bill_id") in receipts else ("row", r.get("id")) for r in rows}
        if len(entries) < 2:
            continue
        first = rows[0]
        found.append({
            "date": day.isoformat(),
            "amount": amount,
            "description": clean_name(first.get("description")),
            "shop": clean_name(first.get("shop")),
            "category": _category(first),
            "count": len(entries),
            "ids": sorted(r["id"] for r in rows if r.get("id") is not None),
        })

    found.sort(key=lambda i: (i["date"], i["amount"]), reverse=True)
    return {"recent_days": recent_days, "items": found[:top], "total_found": len(found)}


__all__ = ["unusual_expenses", "possible_duplicates"]
