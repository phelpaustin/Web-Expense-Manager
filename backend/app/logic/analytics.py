"""Pure analytics logic, ported from the Streamlit app's analytics.py.

The original functions mixed calculations with Streamlit rendering
(st.subheader, st.line_chart, st.cache_data, ...). Here we keep ONLY the
calculations: plain data in, plain data out. That makes them reusable by the
API, by tests, and by a future mobile app — none of which know about Streamlit.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from app.logic.frame import frame
from app.core.money import as_decimal, quantize_money

def _to_frame(expenses: list[dict]) -> pd.DataFrame:
    if not expenses:
        return pd.DataFrame(columns=["date", "category", "amount"])
    return frame(expenses, ["date", "category", "amount"])


def monthly_totals(expenses: list[dict]) -> list[dict]:
    """Total spend per calendar month, sorted ascending (was monthly_agg_for_forecast)."""
    df = _to_frame(expenses)
    if df.empty:
        return []
    df["month"] = df["date"].dt.to_period("M").astype(str)
    monthly = df.groupby("month")["amount"].sum().reset_index().sort_values("month")
    return [{"month": row.month, "total": quantize_money(row.amount)} for row in monthly.itertuples()]


def current_month_key(today: date | None = None) -> str:
    today = today or date.today()
    return f"{today.year:04d}-{today.month:02d}"


def complete_months(monthly: list[dict], today: date | None = None) -> list[dict]:
    """Monthly totals for finished calendar months only.

    The in-progress month is dropped (a part-month total is not comparable to
    full months), and calendar gaps between the first and last finished month
    are filled with zero so "previous month" really means the previous month,
    not "the previous month that had data".
    """
    current = current_month_key(today)
    done = {m["month"]: m["total"] for m in monthly if m["month"] < current}
    if not done:
        return []
    first = pd.Period(min(done), freq="M")
    last = pd.Period(current, freq="M") - 1
    return [
        {"month": str(p), "total": done.get(str(p), quantize_money(0))}
        for p in pd.period_range(first, last, freq="M")
    ]


def month_over_month_change(monthly: list[dict], today: date | None = None) -> dict | None:
    """% change of the last finished month vs the one before it.

    Never includes the current, partial month. pct_change is None when the
    earlier month had no spend (a percentage would be meaningless).
    """
    done = complete_months(monthly, today)
    if len(done) < 2:
        return None
    last, prev = done[-1], done[-2]
    delta = last["total"] - prev["total"]
    pct = round(float(delta / prev["total"] * 100), 1) if prev["total"] else None
    return {
        "last": last["total"],
        "previous": prev["total"],
        "last_month": last["month"],
        "previous_month": prev["month"],
        "pct_change": pct,
        "direction": "up" if delta > 0 else "down" if delta < 0 else "flat",
    }


def category_breakdown(expenses: list[dict]) -> list[dict]:
    """Per-category totals, share, and avg cost per purchase (was category_insights)."""
    df = _to_frame(expenses)
    if df.empty:
        return []
    total = quantize_money(df["amount"].sum())
    grouped = (
        df.groupby("category")
        .agg(total=("amount", "sum"), count=("amount", "count"))
        .reset_index()
        .sort_values("total", ascending=False)
    )
    result = []
    for row in grouped.itertuples():
        count = int(row.count)
        cat_total = quantize_money(row.total)
        result.append(
            {
                "category": row.category,
                "total": cat_total,
                "count": count,
                "avg_per_purchase": quantize_money(cat_total / count) if count else quantize_money(0),
                "pct_of_total": round(cat_total / total * 100, 1) if total else 0.0,
            }
        )
    return result
