"""Pure financial-metrics logic, ported from financial_metrics.py.

Savings rate, cash flow, burn rate, and expense volatility — computed from
plain expense/income dicts (no Streamlit).
"""
from __future__ import annotations

import calendar
from datetime import date

import pandas as pd

from app.logic import analytics, income as income_logic


def _current_month_key() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def summary(expenses: list[dict], income: list[dict]) -> dict:
    exp_monthly = analytics.monthly_totals(expenses)
    inc_monthly = income_logic.monthly_totals(income)
    exp_map = {m["month"]: m["total"] for m in exp_monthly}
    inc_map = {m["month"]: m["total"] for m in inc_monthly}

    cur = _current_month_key()
    this_spent = exp_map.get(cur, 0.0)
    this_income = inc_map.get(cur, 0.0)

    monthly_savings = round(this_income - this_spent, 2)
    savings_rate = round(monthly_savings / this_income * 100, 1) if this_income > 0 else 0.0

    today = date.today()
    days_elapsed = max(today.day, 1)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    daily_burn = round(this_spent / days_elapsed, 2)
    monthly_projection = round(daily_burn * days_in_month, 2)

    vals = [m["total"] for m in exp_monthly]
    if len(vals) >= 2:
        series = pd.Series(vals)
        mean = float(series.mean())
        std = float(series.std())
        cv = round(std / mean * 100, 1) if mean > 0 else 0.0
    else:
        cv = 0.0

    months = sorted(set(exp_map) | set(inc_map))
    cash_flow = []
    cumulative = 0.0
    for m in months:
        exp = round(exp_map.get(m, 0.0), 2)
        inc = round(inc_map.get(m, 0.0), 2)
        cf = round(inc - exp, 2)
        cumulative = round(cumulative + cf, 2)
        cash_flow.append({"month": m, "income": inc, "expenses": exp, "cash_flow": cf, "cumulative": cumulative})

    return {
        "this_month_income": round(this_income, 2),
        "this_month_spent": round(this_spent, 2),
        "monthly_savings": monthly_savings,
        "savings_rate": savings_rate,
        "daily_burn": daily_burn,
        "monthly_projection": monthly_projection,
        "volatility_cv": cv,
        "cash_flow": cash_flow,
    }
