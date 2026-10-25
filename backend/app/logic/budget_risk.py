"""How likely is each budget to be exceeded by the end of its period?

The question
  You have spent S of a budget B and the period has D days left. Will the rest of the period's
  spending go past the room you have left, H = B - S?

How it is answered
  By looking at what actually happened in earlier periods over the same stretch: the days
  *after this same point* (after the 21st of the month, after Wednesday of the week). Each past
  period gives one sample, "how much was spent in those days". The estimate is the share of
  past periods in which that was more than H. Because the days line up, things that always
  land at the same time (rent on the 1st, a bill on the 28th, payday shopping) are counted
  where they belong, which a straight-line projection cannot do: spending a lot on day 1 does not
  mean you will keep spending at that rate.

  The share is nudged away from 0% and 100% ((k + 0.5) / (n + 1)) because a few past periods can
  never prove something is impossible or certain. It needs at least MIN_PERIODS earlier periods
  (at most the last MAX_PERIODS are used); with less history it says so rather than guess.

What it covers
  Category budgets (always the calendar month, as everywhere else) and the total budget in its
  chosen period (weekly, monthly, or annual-to-date, whose period ends with the month), with the same
  spent, limit and rollover as the budget bars, because it takes those from the caller.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from app.core.money import as_decimal, quantize_money
from app.logic.category_change import _as_date
from app.logic.spending_mix import shift_month

MIN_PERIODS = 4
MAX_PERIODS = 12
ALERT_THRESHOLD = 75.0  # percent: an alert is worth raising at or above this chance

LEVELS = (  # (lower bound in percent, name)
    (75.0, "very_likely"),
    (50.0, "likely"),
    (25.0, "possible"),
    (0.0, "unlikely"),
)


def level_for(probability: float) -> str:
    return next(name for floor, name in LEVELS if probability >= floor)


def _day_totals(expenses: list[dict], today: date) -> tuple[dict[date, Decimal], dict[str, dict[date, Decimal]]]:
    """Spending per day: overall, and per category. Future-dated rows are ignored."""
    overall: dict[date, Decimal] = defaultdict(Decimal)
    by_category: dict[str, dict[date, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for e in expenses:
        d = _as_date(e.get("date"))
        amount = as_decimal(e.get("amount"))
        if d is None or d > today or amount <= 0:
            continue
        overall[d] += amount
        by_category[str(e.get("category") or "")][d] += amount
    return overall, by_category


def remainders(days: dict[date, Decimal], align: str, today: date, drop_partial_start: bool) -> list[Decimal]:
    """Spending in the days after this same point of each earlier period, oldest first.

    `align` is "month" (days after today's day-of-month) or "week" (days after today's weekday).
    The current period is not included. With `drop_partial_start`, a first period that began after
    the window had already opened is left out, since part of it was never recorded.
    """
    if not days:
        return []
    if align == "week":
        cut = today.weekday()
        position = lambda d: d.weekday()
        period_of = lambda d: d - timedelta(days=d.weekday())
        current = period_of(today)
        step = lambda p: p + timedelta(days=7)
    else:
        cut = today.day
        position = lambda d: d.day - 1
        period_of = lambda d: d.replace(day=1)
        current = period_of(today)
        step = lambda p: shift_month(p, 1)
        cut = today.day - 1  # zero-based, like position()
    first_day = min(days)
    sums: dict[date, Decimal] = defaultdict(Decimal)
    for d, amount in days.items():
        if position(d) > cut:
            sums[period_of(d)] += amount

    periods, p = [], period_of(first_day)
    if drop_partial_start and position(first_day) > cut + 1:
        p = step(p)  # recording began after the window opened: that period is incomplete
    while p < current:
        periods.append(p)
        p = step(p)
    return [sums.get(p, Decimal(0)) for p in periods[-MAX_PERIODS:]]


def _blank(category: str, is_total: bool, period: str, label: str, limit, spent, remaining, pct, days_remaining: int, align: str, anchor: int) -> dict:
    return {
        "category": category, "is_total": is_total, "period": period, "label": label,
        "limit": quantize_money(limit), "spent": quantize_money(spent), "remaining": quantize_money(remaining), "pct": pct,
        "days_remaining": days_remaining, "align": align, "anchor": anchor,
        "available": False, "reason": None, "probability": None, "level": None,
        "samples": 0, "exceeded": 0, "typical_remaining": None,
    }


def _assess(item: dict, days: dict[date, Decimal], today: date, drop_partial_start: bool) -> dict:
    headroom = as_decimal(item["remaining"])
    if headroom < 0:  # already over: nothing to estimate
        return {**item, "available": True, "probability": 100.0, "level": "over"}
    if item["days_remaining"] <= 0:  # the period ends today and the budget held
        return {**item, "available": True, "probability": 0.0, "level": "unlikely"}
    samples = remainders(days, item["align"], today, drop_partial_start)
    if len(samples) < MIN_PERIODS:
        return {**item, "reason": "not_enough_history", "samples": len(samples)}
    exceeded = sum(1 for r in samples if r > headroom)
    probability = round((exceeded + 0.5) / (len(samples) + 1) * 100, 1)
    return {
        **item, "available": True, "probability": probability, "level": level_for(probability),
        "samples": len(samples), "exceeded": exceeded, "typical_remaining": quantize_money(median(samples)),
    }


def budget_risk(expenses: list[dict], category_statuses: list[dict], period_status: dict | None, today: date | None = None) -> dict:
    """The chance of exceeding each budget by the end of its period.

    `category_statuses` and `period_status` are the budget bars' own numbers (see
    logic.budgets), so the limit, spent and rollover match what is shown.
    """
    today = today or date.today()
    overall, by_category = _day_totals(expenses, today)
    month_days_left = calendar.monthrange(today.year, today.month)[1] - today.day

    items = []
    if period_status:
        weekly = period_status["period"] == "Weekly"
        item = _blank(
            "Total", True, period_status["period"], period_status["label"], period_status["effective"], period_status["spent"],
            period_status["remaining"], period_status["pct"], period_status["days_remaining"],
            "week" if weekly else "month", today.weekday() if weekly else today.day,
        )
        items.append(_assess(item, overall, today, drop_partial_start=True))
    for status in category_statuses:
        if status["category"] == "Total" or as_decimal(status["budget"]) <= 0:
            continue
        item = _blank(
            status["category"], False, "Monthly", today.strftime("%B %Y"), status["budget"], status["spent"], status["remaining"],
            status["pct"], month_days_left, "month", today.day,
        )
        items.append(_assess(item, by_category.get(status["category"], {}), today, drop_partial_start=False))

    items.sort(key=lambda i: (not i["available"], -(i["probability"] or 0.0), not i["is_total"], i["category"].casefold()))
    return {
        "today": today.isoformat(),
        "has_budgets": bool(items),
        "items": items,
        "min_periods": MIN_PERIODS,
        "alert_threshold": ALERT_THRESHOLD,
    }
