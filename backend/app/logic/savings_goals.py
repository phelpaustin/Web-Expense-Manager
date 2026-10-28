"""Savings goals: how far along each is, what it needs per month, and where the current pace leads.

A goal is a target amount (optionally by a date); how much is saved is the sum of its contributions
(deposits positive, withdrawals negative). The API does not accept a contribution dated in the
future, so every contribution counts. Everything is in the goal's own currency, so there is no
conversion.

Pace. The recent pace is what was put in over the last 90 days (or since the first contribution, if
that is more recent), per 30.4-day month, never averaged over less than one month so a first deposit
does not look like a month's saving. The projected date is when that pace would reach the target.

Status:
  reached      saved >= target
  overdue      the target date has passed and it is not reached
  on_track     a target date, and the recent pace gets there by it
  behind       a target date, and the recent pace (or none) does not
  no_deadline  no target date; the projection is shown if there is a pace

Pure functions on plain dicts.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal

from app.core.money import as_decimal, quantize_money
from app.logic.price_tracker import _as_day

PACE_DAYS = 90
DAYS_PER_MONTH = Decimal("30.4375")
MAX_PROJECTION_MONTHS = 1200       # a pace that would take a century is no projection at all


def saved_total(contributions: list[dict]) -> Decimal:
    return sum((as_decimal(c.get("amount")) for c in contributions if _as_day(c.get("date")) is not None), Decimal(0))


def _recent_pace(contributions: list[dict], today: date) -> Decimal:
    window_start = today - timedelta(days=PACE_DAYS - 1)
    dated = [(_as_day(c.get("date")), as_decimal(c.get("amount"))) for c in contributions]
    dated = [(d, a) for d, a in dated if d is not None]
    if not dated:
        return Decimal(0)
    start = max(window_start, min(d for d, _ in dated))
    net = sum((a for d, a in dated if d >= start), Decimal(0))
    months = max(Decimal((today - start).days + 1) / DAYS_PER_MONTH, Decimal(1))
    return net / months


def goal_progress(goal: dict, contributions: list[dict], today: date | None = None) -> dict:
    today = today or date.today()
    target = as_decimal(goal.get("target_amount"))
    target_date = _as_day(goal.get("target_date"))
    saved = saved_total(contributions)
    remaining = max(target - saved, Decimal(0))
    reached = target > 0 and saved >= target
    pace = _recent_pace(contributions, today)

    needed = None
    if target_date and target_date > today and not reached:
        months_left = max(Decimal((target_date - today).days) / DAYS_PER_MONTH, Decimal(1))
        needed = remaining / months_left

    projected = None
    if not reached and pace > 0 and remaining > 0:
        months_to_go = remaining / pace
        if months_to_go <= MAX_PROJECTION_MONTHS:
            projected = today + timedelta(days=math.ceil(months_to_go * DAYS_PER_MONTH))

    if reached:
        status = "reached"
    elif target_date and target_date < today:
        status = "overdue"
    elif target_date:
        status = "on_track" if projected is not None and projected <= target_date else "behind"
    else:
        status = "no_deadline"

    # From the rounded figures that are shown, so the three numbers always add up on screen.
    shortfall = None
    if status == "behind" and needed is not None:
        shortfall = max(quantize_money(needed) - quantize_money(max(pace, Decimal(0))), Decimal(0))

    dated = [d for d in (_as_day(c.get("date")) for c in contributions) if d is not None]
    return {
        "saved": quantize_money(saved),
        "remaining": quantize_money(remaining),
        "pct": round(float(saved / target * 100), 1) if target > 0 else 0.0,
        "reached": reached,
        "status": status,
        "days_left": (target_date - today).days if target_date else None,
        "needed_per_month": None if needed is None else quantize_money(needed),
        "recent_per_month": quantize_money(max(pace, Decimal(0))),
        "shortfall_per_month": None if shortfall is None else quantize_money(shortfall),
        "projected_date": projected.isoformat() if projected else None,
        "contribution_count": len(contributions),
        "last_contribution": max(dated).isoformat() if dated else None,
    }


def sort_goals(goals: list[dict]) -> list[dict]:
    """Unfinished goals first: the nearest target date, then goals with no date, then the reached ones."""
    def key(g: dict):
        reached = g["status"] == "reached"
        when = str(g["target_date"]) if g.get("target_date") else "9999-12-31"      # a date or its ISO text: both sort alike
        return (reached, when, (g.get("name") or "").lower(), g.get("id") or 0)
    return sorted(goals, key=key)


def summary(goals: list[dict]) -> dict:
    """Counts only: goals may be in different currencies, so amounts are never added together."""
    return {
        "goals": len(goals),
        "reached": sum(1 for g in goals if g["status"] == "reached"),
        "behind": sum(1 for g in goals if g["status"] in ("behind", "overdue")),
    }
