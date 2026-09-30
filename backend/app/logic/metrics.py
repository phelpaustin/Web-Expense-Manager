"""Pure financial-metrics logic, ported from financial_metrics.py.

Savings rate, cash flow, burn rate, and expense volatility — computed from
plain expense/income dicts (no Streamlit).
"""
from __future__ import annotations

import calendar
from datetime import date

from app.logic import analytics, income as income_logic

from app.core.money import quantize_money


def _current_month_key() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def summary(expenses: list[dict], income: list[dict]) -> dict:
    exp_monthly = analytics.monthly_totals(expenses)
    inc_monthly = income_logic.monthly_totals(income)
    exp_map = {m["month"]: m["total"] for m in exp_monthly}
    inc_map = {m["month"]: m["total"] for m in inc_monthly}

    cur = _current_month_key()
    this_spent = exp_map.get(cur, quantize_money(0))
    this_income = inc_map.get(cur, quantize_money(0))

    monthly_savings = round(this_income - this_spent, 2)
    savings_rate = round(monthly_savings / this_income * 100, 1) if this_income > 0 else 0.0

    today = date.today()
    days_elapsed = max(today.day, 1)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    daily_burn = round(this_spent / days_elapsed, 2)
    monthly_projection = round(daily_burn * days_in_month, 2)

    vals = [m["total"] for m in exp_monthly]
    if len(vals) >= 2:
        mean = sum(vals, quantize_money(0)) / len(vals)
        variance = sum((value - mean) ** 2 for value in vals) / (len(vals) - 1)
        std = variance.sqrt()
        cv = round(std / mean * 100, 1) if mean > 0 else 0.0
    else:
        cv = 0.0

    months = sorted(set(exp_map) | set(inc_map))
    cash_flow = []
    cumulative = quantize_money(0)
    for m in months:
        exp = quantize_money(exp_map.get(m, 0))
        inc = quantize_money(inc_map.get(m, 0))
        cf = quantize_money(inc - exp)
        cumulative = quantize_money(cumulative + cf)
        cash_flow.append({"month": m, "income": inc, "expenses": exp, "cash_flow": cf, "cumulative": cumulative})

    return {
        "this_month_income": quantize_money(this_income),
        "this_month_spent": quantize_money(this_spent),
        "monthly_savings": monthly_savings,
        "savings_rate": savings_rate,
        "daily_burn": daily_burn,
        "monthly_projection": monthly_projection,
        "volatility_cv": cv,
        "cash_flow": cash_flow,
    }
