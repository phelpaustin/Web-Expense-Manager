"""Pure budget logic, ported from the Streamlit app's budget_manager.py.

Dropped from the original: JsonStore persistence, theme handling, and every
`_render_*` function (they built HTML via st.markdown). Kept: the spending-vs-
budget calculations and the status thresholds. Budgets are passed in as a plain
dict instead of being read from disk, so this stays storage-agnostic.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

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
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def _category_budgets_only(budgets: dict) -> dict:
    return {k: v for k, v in budgets.items() if k not in (TOTAL_BUDGET_KEY, BUDGET_CONFIG_KEY)}


def total_spending_for_month(expenses: list[dict], month: str | None = None) -> float:
    """Sum spending for a 'YYYY-MM' month (defaults to the current month)."""
    df = _to_frame(expenses)
    if df.empty:
        return 0.0
    target = pd.Period(month, "M") if month else pd.Timestamp.now().to_period("M")
    df["_ym"] = df["date"].dt.to_period("M")
    return round(float(df.loc[df["_ym"] == target, "amount"].sum()), 2)


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
        spent = float(category_spending.get(category, 0.0))
        remaining = budget - spent
        pct = (spent / budget * 100) if budget > 0 else 0.0
        statuses.append(
            {
                "category": category,
                "budget": round(float(budget), 2),
                "spent": round(spent, 2),
                "remaining": round(remaining, 2),
                "pct": round(pct, 1),
                "status": _status_for(pct),
            }
        )

    total_budget = budgets.get(TOTAL_BUDGET_KEY)
    total_spent = total_spending_for_month(expenses, month)

    if total_budget:
        remaining = total_budget - total_spent
        pct = (total_spent / total_budget * 100) if total_budget > 0 else 0.0
        statuses.insert(0, {
            "category": "Total",
            "budget": round(float(total_budget), 2),
            "spent": round(total_spent, 2),
            "remaining": round(remaining, 2),
            "pct": round(pct, 1),
            "status": _status_for(pct),
        })
    elif statuses:
        tb = sum(s["budget"] for s in statuses)
        ts = sum(s["spent"] for s in statuses)
        pct = (ts / tb * 100) if tb > 0 else 0.0
        statuses.insert(0, {
            "category": "Total",
            "budget": round(tb, 2),
            "spent": round(ts, 2),
            "remaining": round(tb - ts, 2),
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
        end = date(when.year, 12, 31)
        label = str(when.year)
    else:  # Monthly
        start = when.replace(day=1)
        end = (date(when.year, 12, 31) if when.month == 12
               else date(when.year, when.month + 1, 1) - timedelta(days=1))
        label = f"{when:%B %Y}"
    return start, end, label, (end - start).days + 1


def spending_in_range(expenses: list[dict], start: date, end: date) -> float:
    total = 0.0
    for e in expenses:
        d = _as_date(e.get("date"))
        if d is not None and start <= d <= end:
            total += float(e.get("amount") or 0.0)
    return round(total, 2)


def rollover_available(expenses, budget, period, current_start, lookback=24) -> float:
    """Net unspent budget carried from prior periods within the data range."""
    if not budget or budget <= 0 or not expenses:
        return 0.0
    dates = [d for d in (_as_date(e.get("date")) for e in expenses) if d is not None]
    if not dates:
        return 0.0
    earliest = min(dates)
    carry = 0.0
    cursor = current_start
    for _ in range(lookback):
        prev_end = cursor - timedelta(days=1)
        if prev_end < earliest:
            break
        p_start, p_end, _lbl, _tot = current_period_range(period, prev_end)
        carry += budget - spending_in_range(expenses, p_start, p_end)
        cursor = p_start
    return round(carry, 2)


def period_budget_status(expenses: list[dict], budget: float, period: str, rollover: bool) -> dict | None:
    """Current-period budget status honouring period + rollover."""
    if not budget:
        return None
    period = period if period in BUDGET_PERIODS else "Monthly"
    start, end, label, total_days = current_period_range(period)
    spent = spending_in_range(expenses, start, end)
    roll = rollover_available(expenses, budget, period, start) if rollover else 0.0
    effective = budget + roll
    remaining = effective - spent
    pct = (spent / effective * 100) if effective > 0 else 0.0
    today = date.today()
    days_elapsed = max((min(today, end) - start).days + 1, 1)
    projected = (spent / days_elapsed) * total_days
    return {
        "period": period,
        "label": label,
        "budget": round(float(budget), 2),
        "rollover": round(roll, 2),
        "effective": round(effective, 2),
        "spent": round(spent, 2),
        "remaining": round(remaining, 2),
        "pct": round(pct, 1),
        "projected": round(projected, 2),
        "days_total": total_days,
        "days_elapsed": days_elapsed,
        "days_remaining": max(total_days - days_elapsed, 0),
        "status": _status_for(pct),
    }
