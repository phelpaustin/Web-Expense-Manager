"""Pure budget logic, ported from the Streamlit app's budget_manager.py.

Dropped from the original: JsonStore persistence, theme handling, and every
`_render_*` function (they built HTML via st.markdown). Kept: the spending-vs-
budget calculations and the status thresholds. Budgets are passed in as a plain
dict instead of being read from disk, so this stays storage-agnostic.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd

from app.core.money import as_decimal, quantize_money

# Sentinel key for the overall monthly budget inside the budgets dict.
TOTAL_BUDGET_KEY = "__total_monthly__"
# Config sentinel (period/rollover) — reserved, excluded from category budgets.
BUDGET_CONFIG_KEY = "__config__"

BUDGET_PERIODS = ["Weekly", "Monthly", "Annual"]


def _status_for(pct: float) -> str:
    return "exceeded" if pct >= 100 else "warning" if pct >= 85 else "caution" if pct >= 60 else "ok"


def _to_frame(expenses: list[dict]) -> pd.DataFrame:
    if not expenses:
        return pd.DataFrame(columns=["date", "category", "amount"])
    df = pd.DataFrame(expenses)
    df["amount"] = df["amount"].map(lambda value: as_decimal(value) if not pd.isna(value) else as_decimal(0))
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def _category_budgets_only(budgets: dict) -> dict:
    return {k: v for k, v in budgets.items() if k not in (TOTAL_BUDGET_KEY, BUDGET_CONFIG_KEY)}


def total_spending_for_month(expenses: list[dict], month: str | None = None) -> Decimal:
    """Sum spending for a 'YYYY-MM' month (defaults to the current month)."""
    df = _to_frame(expenses)
    if df.empty:
        return quantize_money(0)
    target = pd.Period(month, "M") if month else pd.Timestamp.now().to_period("M")
    df["_ym"] = df["date"].dt.to_period("M")
    return quantize_money(df.loc[df["_ym"] == target, "amount"].sum())


def calculate_budget_status(expenses: list[dict], budgets: dict, month: str | None = None) -> list[dict]:
    """Spending vs budget per category for a month, with a prepended 'Total' row."""
    df = _to_frame(expenses)
    if df.empty and not budgets:
        return []

    target = pd.Period(month, "M") if month else pd.Timestamp.now().to_period("M")
    if not df.empty:
        df["_ym"] = df["date"].dt.to_period("M")
        month_df = df[df["_ym"] == target]
        category_spending = month_df.groupby("category")["amount"].sum().to_dict()
    else:
        category_spending = {}

    cat_budgets = _category_budgets_only(budgets)

    statuses: list[dict] = []
    for category, budget in cat_budgets.items():
        spent = quantize_money(category_spending.get(category, 0))
        budget = quantize_money(budget)
        remaining = budget - spent
        pct = (spent / budget * 100) if budget > 0 else 0.0
        statuses.append(
            {
                "category": category,
                "budget": budget,
                "spent": spent,
                "remaining": quantize_money(remaining),
                "pct": round(pct, 1),
                "status": _status_for(pct),
            }
        )

    total_budget = budgets.get(TOTAL_BUDGET_KEY)
    total_spent = total_spending_for_month(expenses, month)

    if total_budget:
        total_budget = quantize_money(total_budget)
        remaining = total_budget - total_spent
        pct = (total_spent / total_budget * 100) if total_budget > 0 else 0.0
        statuses.insert(0, {
            "category": "Total",
            "budget": quantize_money(total_budget),
            "spent": total_spent,
            "remaining": quantize_money(remaining),
            "pct": round(pct, 1),
            "status": _status_for(pct),
        })
    elif statuses:
        tb = sum(s["budget"] for s in statuses)
        ts = sum(s["spent"] for s in statuses)
        pct = (ts / tb * 100) if tb > 0 else 0.0
        statuses.insert(0, {
            "category": "Total",
            "budget": quantize_money(tb),
            "spent": quantize_money(ts),
            "remaining": quantize_money(tb - ts),
            "pct": round(pct, 1),
            "status": _status_for(pct),
        })

    return statuses


# ── Flexible periods (weekly / monthly / annual) + rollover ────────────
def _as_date(value) -> date | None:
    if isinstance(value, date):
        return value
    ts = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(ts) else ts.date()


def current_period_range(period: str, when: date | None = None):
    """Return (start, end, label, total_days) for the period containing *when*."""
    when = when or date.today()
    if period == "Weekly":
        start = when - timedelta(days=when.weekday())
        end = start + timedelta(days=6)
        label = f"Week of {start:%b %d}"
    elif period == "Annual":
        start = date(when.year, 1, 1)
        end = (
            date(when.year, 12, 31)
            if when.month == 12
            else date(when.year, when.month + 1, 1) - timedelta(days=1)
        )
        label = f"YTD through {when:%B %Y}"
    else:  # Monthly
        start = when.replace(day=1)
        end = (date(when.year, 12, 31) if when.month == 12
               else date(when.year, when.month + 1, 1) - timedelta(days=1))
        label = f"{when:%B %Y}"
    return start, end, label, (end - start).days + 1


def allocated_period_budget(monthly_budget, period: str, when: date | None = None) -> Decimal:
    """Convert a monthly allocation to the selected period's budget."""
    when = when or date.today()
    monthly_budget = quantize_money(monthly_budget)
    if period == "Weekly":
        month_start = when.replace(day=1)
        month_end = (
            date(when.year, 12, 31)
            if when.month == 12
            else date(when.year, when.month + 1, 1) - timedelta(days=1)
        )
        first_week = month_start - timedelta(days=month_start.weekday())
        last_week = month_end - timedelta(days=month_end.weekday())
        weeks_in_month = ((last_week - first_week).days // 7) + 1
        return quantize_money(monthly_budget / Decimal(weeks_in_month))
    if period == "Annual":
        return quantize_money(monthly_budget * Decimal(when.month))
    return monthly_budget


def spending_in_range(expenses: list[dict], start: date, end: date) -> Decimal:
    total = quantize_money(0)
    for e in expenses:
        d = _as_date(e.get("date"))
        if d is not None and start <= d <= end:
            total += quantize_money(e.get("amount"))
    return quantize_money(total)


def rollover_available(expenses, budget, period, current_start, lookback=24) -> Decimal:
    """Net unspent budget carried from prior periods within the data range."""
    if not budget or budget <= 0 or not expenses:
        return quantize_money(0)
    dates = [d for d in (_as_date(e.get("date")) for e in expenses) if d is not None]
    if not dates:
        return quantize_money(0)
    earliest = min(dates)
    budget = quantize_money(budget)
    carry = quantize_money(0)
    cursor = current_start
    for _ in range(lookback):
        prev_end = cursor - timedelta(days=1)
        if prev_end < earliest:
            break
        p_start, p_end, _lbl, _tot = current_period_range(period, prev_end)
        budget_date = p_end if period == "Annual" else p_start
        period_budget = allocated_period_budget(budget, period, budget_date)
        carry += period_budget - spending_in_range(expenses, p_start, p_end)
        cursor = p_start
    return quantize_money(carry)


def period_budget_status(
    expenses: list[dict], budget: Decimal, period: str, rollover: bool, when: date | None = None
) -> dict | None:
    """Current-period budget status honouring period + rollover."""
    if not budget:
        return None
    period = period if period in BUDGET_PERIODS else "Monthly"
    today = when or date.today()
    start, end, label, total_days = current_period_range(period, today)
    spent = spending_in_range(expenses, start, end)
    monthly_budget = quantize_money(budget)
    budget = allocated_period_budget(monthly_budget, period, today)
    roll = rollover_available(expenses, monthly_budget, period, start) if rollover else quantize_money(0)
    effective = budget + roll
    remaining = effective - spent
    pct = (spent / effective * 100) if effective > 0 else 0.0
    days_elapsed = max((min(today, end) - start).days + 1, 1)
    projected = (spent / days_elapsed) * total_days
    return {
        "period": period,
        "label": label,
        "budget": budget,
        "rollover": quantize_money(roll),
        "effective": quantize_money(effective),
        "spent": quantize_money(spent),
        "remaining": quantize_money(remaining),
        "pct": round(pct, 1),
        "projected": quantize_money(projected),
        "days_total": total_days,
        "days_elapsed": days_elapsed,
        "days_remaining": max(total_days - days_elapsed, 0),
        "status": _status_for(pct),
    }
