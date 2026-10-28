"""Yearly and monthly spending report.

One function builds the whole report for a calendar year or one month from converted expenses (and
income) as plain dicts; the endpoint, the Excel file and the PDF all use that one result, so the
screen and the files can never disagree.

A report holds: totals (spent, income, net, savings rate, daily/monthly average), the change from
the previous year/month, spending by category (amount and share), spending over the period (by
month for a year, by day for a month) with its peak, a category-by-month table for a year, the top
shops and the largest single expenses. Every expense counts, refunds included, so the total equals
the one on the dashboard. Categories and shops that differ only in case or spacing are one.

Pure functions: no DB, no FastAPI.
"""
from __future__ import annotations

from calendar import monthrange
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

from app.core.money import as_decimal, quantize_money
from app.logic.names import clean_name, name_key
from app.logic.price_tracker import _as_day

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
SHORT_MONTHS = [m[:3] for m in MONTH_NAMES]
UNCATEGORISED = "Uncategorised"
TOP_SHOPS = 10
TOP_EXPENSES = 10


def period_label(year: int, month: int | None) -> str:
    return f"{MONTH_NAMES[month - 1]} {year}" if month else str(year)


def period_bounds(year: int, month: int | None) -> tuple[date, date]:
    if month:
        return date(year, month, 1), date(year, month, monthrange(year, month)[1])
    return date(year, 1, 1), date(year, 12, 31)


def previous_period(year: int, month: int | None) -> tuple[int, int | None]:
    if month is None:
        return year - 1, None
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _in_period(day: date | None, start: date, end: date) -> bool:
    return day is not None and start <= day <= end


def _share(part: Decimal, whole: Decimal) -> float:
    return round(float(part / whole * 100), 1) if whole else 0.0


def _display_names(values: list[str]) -> dict[str, str]:
    """name key -> the spelling used most often (ties: alphabetical), so "food" and "Food" are one."""
    counts: dict[str, Counter] = defaultdict(Counter)
    for v in values:
        counts[name_key(v)][clean_name(v)] += 1
    return {k: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] for k, c in counts.items()}


def _total(rows: list[tuple[date, dict, Decimal]]) -> Decimal:
    return sum((a for _, _, a in rows), Decimal(0))


def years_with_data(expenses: list[dict], today: date | None = None) -> list[int]:
    """Years that hold at least one expense, newest first; this year is always offered."""
    today = today or date.today()
    years = {today.year}
    for e in expenses:
        day = _as_day(e.get("date"))
        if day is not None:
            years.add(day.year)
    return sorted(years, reverse=True)


def build_report(
    expenses: list[dict],
    income: list[dict] | None,
    year: int,
    month: int | None = None,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    start, end = period_bounds(year, month)
    prev_year, prev_month = previous_period(year, month)
    prev_start, prev_end = period_bounds(prev_year, prev_month)

    rows: list[tuple[date, dict, Decimal]] = []
    prev_total, prev_count = Decimal(0), 0
    for e in expenses:
        day = _as_day(e.get("date"))
        if day is None:
            continue
        amount = as_decimal(e.get("amount"))
        if start <= day <= end:
            rows.append((day, e, amount))
        elif prev_start <= day <= prev_end:
            prev_total += amount
            prev_count += 1
    spent = _total(rows)

    income_total = sum((as_decimal(i.get("amount")) for i in (income or []) if _in_period(_as_day(i.get("date")), start, end)), Decimal(0))
    net = income_total - spent

    # How much of the period has happened: a report for this month or year is an average over the
    # days so far, a past one over all its days, a future one over none.
    if today < start:
        elapsed_days = elapsed_months = 0
    elif today >= end:
        elapsed_days, elapsed_months = (end - start).days + 1, (1 if month else 12)
    else:
        elapsed_days, elapsed_months = (today - start).days + 1, (1 if month else today.month)

    category_names = _display_names([e.get("category") or UNCATEGORISED for _, e, _ in rows])
    by_category: dict[str, list] = defaultdict(lambda: [Decimal(0), 0])
    for _, e, amount in rows:
        key = name_key(e.get("category") or UNCATEGORISED)
        by_category[key][0] += amount
        by_category[key][1] += 1
    categories = sorted(
        (
            {"category": category_names[k], "total": quantize_money(t), "count": c, "share_pct": _share(t, spent)}
            for k, (t, c) in by_category.items()
        ),
        key=lambda c: (-c["total"], c["category"]),
    )

    if month:
        keys = [date(year, month, d).isoformat() for d in range(1, end.day + 1)]
        labels = [str(d) for d in range(1, end.day + 1)]
        long_labels = [f"{d} {MONTH_NAMES[month - 1]}" for d in range(1, end.day + 1)]
    else:
        keys = [f"{year}-{m:02d}" for m in range(1, 13)]
        labels = SHORT_MONTHS
        long_labels = MONTH_NAMES
    index = {k: i for i, k in enumerate(keys)}
    period_totals = [Decimal(0)] * len(keys)
    period_counts = [0] * len(keys)
    matrix: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal(0)] * 12)
    for day, e, amount in rows:
        i = index[day.isoformat() if month else f"{day.year}-{day.month:02d}"]
        period_totals[i] += amount
        period_counts[i] += 1
        if not month:
            matrix[name_key(e.get("category") or UNCATEGORISED)][day.month - 1] += amount
    periods = [
        {"key": keys[i], "label": labels[i], "total": quantize_money(period_totals[i]), "count": period_counts[i]}
        for i in range(len(keys))
    ]
    peak = None
    if rows:
        top = max(range(len(keys)), key=lambda i: (period_totals[i], -i))
        if period_totals[top] > 0:
            peak = {"key": keys[top], "label": long_labels[top], "total": quantize_money(period_totals[top])}

    category_matrix = None
    if not month:
        order = [name_key(c["category"]) for c in categories]
        category_matrix = {
            "columns": keys,
            "rows": [
                {"category": category_names[k], "values": [quantize_money(v) for v in matrix[k]], "total": quantize_money(sum(matrix[k], Decimal(0)))}
                for k in order
            ],
        }

    shop_names = _display_names([e.get("shop") for _, e, _ in rows if name_key(e.get("shop"))])
    by_shop: dict[str, list] = defaultdict(lambda: [Decimal(0), 0])
    for _, e, amount in rows:
        key = name_key(e.get("shop"))
        if key:
            by_shop[key][0] += amount
            by_shop[key][1] += 1
    top_shops = [
        {"shop": shop_names[k], "total": quantize_money(t), "count": c, "share_pct": _share(t, spent)}
        for k, (t, c) in sorted(by_shop.items(), key=lambda kv: (-kv[1][0], shop_names[kv[0]]))[:TOP_SHOPS]
    ]

    biggest = sorted(rows, key=lambda r: (-r[2], r[0], r[1].get("id") or 0))[:TOP_EXPENSES]
    largest = [
        {
            "date": day.isoformat(),
            "category": clean_name(e.get("category")) or UNCATEGORISED,
            "description": clean_name(e.get("description")),
            "shop": clean_name(e.get("shop")),
            "amount": quantize_money(amount),
        }
        for day, e, amount in biggest
    ]

    return {
        "kind": "month" if month else "year",
        "year": year,
        "month": month,
        "label": period_label(year, month),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "totals": {
            "spent": quantize_money(spent),
            "count": len(rows),
            "income": quantize_money(income_total),
            "net": quantize_money(net),
            "savings_rate_pct": round(float(net / income_total * 100), 1) if income_total > 0 else None,
            "avg_per_day": quantize_money(spent / elapsed_days) if elapsed_days else quantize_money(0),
            "avg_per_month": None if month else (quantize_money(spent / elapsed_months) if elapsed_months else quantize_money(0)),
        },
        "previous": {
            "label": period_label(prev_year, prev_month),
            "spent": quantize_money(prev_total),
            "count": prev_count,
            "change": quantize_money(spent - prev_total),
            "change_pct": round(float((spent - prev_total) / prev_total * 100), 1) if prev_total > 0 else None,
        },
        "categories": categories,
        "periods": periods,
        "peak": peak,
        "category_matrix": category_matrix,
        "top_shops": top_shops,
        "largest": largest,
    }
