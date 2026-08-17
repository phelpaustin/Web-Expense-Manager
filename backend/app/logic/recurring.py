"""Pure recurring-schedule logic, ported from recurring_manager.py.

Kept: the frequency table and the due/catch-up scheduling. Dropped: JsonStore
persistence, Streamlit UI, and the expense-row builder (the API builds rows
against the new schema). Functions take plain values so they're easy to test.
"""
from __future__ import annotations

from datetime import date, timedelta

FREQUENCIES = {
    "Daily": 1,
    "Weekly": 7,
    "Bi-weekly": 14,
    "Monthly": 30,
    "Quarterly": 90,
    "Yearly": 365,
}

# Safety cap so a long-dormant high-frequency template can't post thousands of
# rows in a single catch-up run.
_CATCHUP_CAP = 366


def _freq_days(frequency: str) -> int:
    return FREQUENCIES.get(frequency, 30)


def is_due(last_applied: date | None, frequency: str, today: date | None = None) -> bool:
    today = today or date.today()
    if last_applied is None:
        return True
    return (today - last_applied).days >= _freq_days(frequency)


def due_dates(last_applied: date | None, frequency: str, today: date | None = None) -> list[date]:
    """Every date a template should post on, from after last_applied through today.

    - Never applied → ``[today]`` (single first posting, no back-fill).
    - Applied → one date per missed period (catch-up), bounded by the cap.
    - Not yet due → ``[]``.
    """
    today = today or date.today()
    if last_applied is None:
        return [today]
    days = _freq_days(frequency)
    dates: list[date] = []
    nxt = last_applied + timedelta(days=days)
    while nxt <= today and len(dates) < _CATCHUP_CAP:
        dates.append(nxt)
        nxt = nxt + timedelta(days=days)
    return dates
