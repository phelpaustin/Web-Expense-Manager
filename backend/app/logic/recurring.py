"""Calendar-aware recurring schedule logic.

Month-based schedules stay anchored to their original scheduled date. If that
date is the last day of its month, every occurrence stays on the last day of
the target month. Otherwise, short months clamp to their last day and later
months return to the original day (for example, January 30 → February 28 →
March 30).
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

# Values are (unit, amount); month-based intervals are calendar periods, not
# approximations in days.
FREQUENCIES = {
    "Daily": ("days", 1),
    "Weekly": ("days", 7),
    "Bi-weekly": ("days", 14),
    "Monthly": ("months", 1),
    "Quarterly": ("months", 3),
    "Yearly": ("months", 12),
}

# Safety cap so a long-dormant high-frequency template can't post thousands of
# rows in a single catch-up run.
_CATCHUP_CAP = 366


def _frequency_parts(frequency: str) -> tuple[str, int]:
    return FREQUENCIES.get(frequency, ("months", 1))


def _add_months(anchor: date, months: int) -> date:
    month_index = anchor.year * 12 + anchor.month - 1 + months
    year, month_zero_based = divmod(month_index, 12)
    month = month_zero_based + 1
    target_month_end = calendar.monthrange(year, month)[1]
    anchor_is_month_end = anchor.day == calendar.monthrange(anchor.year, anchor.month)[1]
    day = target_month_end if anchor_is_month_end else min(anchor.day, target_month_end)
    return date(year, month, day)


def _date_at_period(anchor: date, frequency: str, period: int) -> date:
    unit, amount = _frequency_parts(frequency)
    if unit == "days":
        return anchor + timedelta(days=amount * period)
    return _add_months(anchor, amount * period)


def _first_period_after(anchor: date, last_applied: date, frequency: str) -> int:
    unit, amount = _frequency_parts(frequency)
    if unit == "days":
        elapsed = (last_applied - anchor).days
        period = max(0, elapsed // amount)
    else:
        elapsed_months = (last_applied.year - anchor.year) * 12 + last_applied.month - anchor.month
        period = max(0, elapsed_months // amount)

    while _date_at_period(anchor, frequency, period) <= last_applied:
        period += 1
    while period > 0 and _date_at_period(anchor, frequency, period - 1) > last_applied:
        period -= 1
    return period


def is_due(
    last_applied: date | None,
    frequency: str,
    today: date | None = None,
    schedule_anchor: date | None = None,
) -> bool:
    today = today or date.today()
    if last_applied is None:
        return True
    return bool(due_dates(last_applied, frequency, today, schedule_anchor))


def due_dates(
    last_applied: date | None,
    frequency: str,
    today: date | None = None,
    schedule_anchor: date | None = None,
) -> list[date]:
    """Every scheduled date after ``last_applied`` through today.

    Never applied templates produce one first posting on ``today``. Calendar
    intervals use the persistent anchor so month-end dates don't drift after a
    short month. Catch-up dates are bounded by ``_CATCHUP_CAP``.
    """
    today = today or date.today()
    if last_applied is None:
        return [today]

    unit, amount = _frequency_parts(frequency)
    if unit == "days":
        dates: list[date] = []
        nxt = last_applied + timedelta(days=amount)
        while nxt <= today and len(dates) < _CATCHUP_CAP:
            dates.append(nxt)
            nxt += timedelta(days=amount)
        return dates

    anchor = schedule_anchor or last_applied
    period = _first_period_after(anchor, last_applied, frequency)
    dates = []
    while len(dates) < _CATCHUP_CAP:
        nxt = _date_at_period(anchor, frequency, period)
        if nxt > today:
            break
        dates.append(nxt)
        period += 1
    return dates


def backfill_dates(start: date, end: date, frequency: str) -> list[date]:
    """Return scheduled dates from ``start`` through ``end`` (inclusive).

    ``start`` anchors month-based recurrences. Month-end starts stay at month
    end; other dates preserve their day where possible and clamp in short
    months, then return to the original day in longer months.
    """
    if start > end:
        return []

    dates: list[date] = []
    period = 0
    while len(dates) < _CATCHUP_CAP:
        scheduled = _date_at_period(start, frequency, period)
        if scheduled > end:
            break
        dates.append(scheduled)
        period += 1
    return dates
