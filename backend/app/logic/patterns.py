"""When you spend: which weekdays and which part of the month.

Everything is averaged per calendar day in the window, not per expense, because a window holds a
different number of Mondays than Sundays (and of days 29-31 than days 1-7). Payments posted by a
recurring template are left out by default: they land on their due date by design, so they would
only show when the rent is due. Refunds and zero amounts are ignored. Too little history says so
(`enough` is false) instead of drawing a pattern from a handful of purchases.

Pure functions on plain dicts.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.core.money import as_decimal, quantize_money
from app.logic.price_tracker import _as_day, _months_ago_start

DEFAULT_MONTHS = 6
MIN_EXPENSES = 20
MIN_DAYS = 28

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# Day-of-month parts: the first week, the second, the third, and the rest (days 22-31).
MONTH_PARTS = [(1, 7), (8, 14), (15, 21), (22, 31)]


def _part_index(day_of_month: int) -> int:
    for i, (lo, hi) in enumerate(MONTH_PARTS):
        if lo <= day_of_month <= hi:
            return i
    return len(MONTH_PARTS) - 1


def _share(part: Decimal, whole: Decimal) -> float:
    return round(float(part / whole * 100), 1) if whole > 0 else 0.0


def spending_patterns(
    expenses: list[dict],
    today: date | None = None,
    months: int = DEFAULT_MONTHS,
    include_recurring: bool = False,
) -> dict:
    today = today or date.today()
    start = _months_ago_start(today, max(months, 0))

    weekday_days = [0] * 7
    part_days = [0] * len(MONTH_PARTS)
    d = start
    while d <= today:
        weekday_days[d.weekday()] += 1
        part_days[_part_index(d.day)] += 1
        d += timedelta(days=1)
    days = sum(weekday_days)

    weekday_total = [Decimal(0)] * 7
    weekday_count = [0] * 7
    part_total = [Decimal(0)] * len(MONTH_PARTS)
    part_count = [0] * len(MONTH_PARTS)
    for e in expenses:
        day = _as_day(e.get("date"))
        if day is None or day < start or day > today:
            continue
        if not include_recurring and e.get("recurring_template_id") is not None:
            continue
        amount = as_decimal(e.get("amount"))
        if amount <= 0:
            continue
        w, p = day.weekday(), _part_index(day.day)
        weekday_total[w] += amount
        weekday_count[w] += 1
        part_total[p] += amount
        part_count[p] += 1

    spent = sum(weekday_total, Decimal(0))
    count = sum(weekday_count)
    enough = count >= MIN_EXPENSES and days >= MIN_DAYS

    weekdays = [
        {
            "weekday": i,
            "name": WEEKDAYS[i],
            "total": quantize_money(weekday_total[i]),
            "count": weekday_count[i],
            "days": weekday_days[i],
            "per_day": quantize_money(weekday_total[i] / weekday_days[i]) if weekday_days[i] else quantize_money(0),
            "share_pct": _share(weekday_total[i], spent),
        }
        for i in range(7)
    ]
    month_parts = [
        {
            "label": f"{lo}–{hi}",
            "from_day": lo,
            "to_day": hi,
            "total": quantize_money(part_total[i]),
            "count": part_count[i],
            "days": part_days[i],
            "per_day": quantize_money(part_total[i] / part_days[i]) if part_days[i] else quantize_money(0),
            "share_pct": _share(part_total[i], spent),
        }
        for i, (lo, hi) in enumerate(MONTH_PARTS)
    ]

    busiest = quietest = None
    weekend = None
    if enough:
        ranked = sorted(weekdays, key=lambda w: (-w["per_day"], w["weekday"]))
        busiest, quietest = ranked[0]["name"], ranked[-1]["name"]
        weekend_total, weekend_days = weekday_total[5] + weekday_total[6], weekday_days[5] + weekday_days[6]
        other_total, other_days = spent - weekend_total, days - weekend_days
        weekend_per_day = weekend_total / weekend_days if weekend_days else Decimal(0)
        other_per_day = other_total / other_days if other_days else Decimal(0)
        weekend = {
            "per_day": quantize_money(weekend_per_day),
            "weekday_per_day": quantize_money(other_per_day),
            "ratio": round(float(weekend_per_day / other_per_day), 1) if other_per_day > 0 else None,
            "share_pct": _share(weekend_total, spent),
        }

    return {
        "months": months,
        "start": start.isoformat(),
        "end": today.isoformat(),
        "days": days,
        "spent": quantize_money(spent),
        "count": count,
        "enough": enough,
        "weekdays": weekdays,
        "month_parts": month_parts,
        "busiest_weekday": busiest,
        "quietest_weekday": quietest,
        "weekend": weekend,
    }
