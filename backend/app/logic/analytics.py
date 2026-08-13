"""Pure analytics logic, ported from the Streamlit app's analytics.py.

The original functions mixed calculations with Streamlit rendering
(st.subheader, st.line_chart, st.cache_data, ...). Here we keep ONLY the
calculations: plain data in, plain data out. That makes them reusable by the
API, by tests, and by a future mobile app — none of which know about Streamlit.
"""
from __future__ import annotations

import pandas as pd

# statsmodels is optional — forecasting degrades gracefully without it,
# exactly like the HAS_STATS flag in the original module.
try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    HAS_STATS = True
except Exception:
    HAS_STATS = False


def _to_frame(expenses: list[dict]) -> pd.DataFrame:
    if not expenses:
        return pd.DataFrame(columns=["date", "category", "amount"])
    df = pd.DataFrame(expenses)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def monthly_totals(expenses: list[dict]) -> list[dict]:
    """Total spend per calendar month, sorted ascending (was monthly_agg_for_forecast)."""
    df = _to_frame(expenses)
    if df.empty:
        return []
    df["month"] = df["date"].dt.to_period("M").astype(str)
    monthly = df.groupby("month")["amount"].sum().reset_index().sort_values("month")
    return [{"month": row.month, "total": round(float(row.amount), 2)} for row in monthly.itertuples()]


def month_over_month_change(monthly: list[dict]) -> dict | None:
    """% change of the latest month vs the previous one (was the pct_change block)."""
    if len(monthly) < 2:
        return None
    last = monthly[-1]["total"]
    prev = monthly[-2]["total"]
    pct = ((last - prev) / prev * 100) if prev else 0.0
    return {
        "last": last,
        "previous": prev,
        "pct_change": round(pct, 1),
        "direction": "up" if pct > 0 else "down" if pct < 0 else "flat",
    }


def forecast_next_month(monthly: list[dict]) -> float | None:
    """One-step Holt-Winters forecast (was the ExponentialSmoothing block)."""
    if not HAS_STATS or len(monthly) < 2:
        return None
    series = pd.Series([m["total"] for m in monthly])
    try:
        fit = ExponentialSmoothing(series, trend="add", seasonal=None).fit()
        return round(float(fit.forecast(1).iloc[0]), 2)
    except Exception:
        return None


def category_breakdown(expenses: list[dict]) -> list[dict]:
    """Per-category totals, share, and avg cost per purchase (was category_insights)."""
    df = _to_frame(expenses)
    if df.empty:
        return []
    total = float(df["amount"].sum())
    grouped = (
        df.groupby("category")
        .agg(total=("amount", "sum"), count=("amount", "count"))
        .reset_index()
        .sort_values("total", ascending=False)
    )
    result = []
    for row in grouped.itertuples():
        count = int(row.count)
        cat_total = float(row.total)
        result.append(
            {
                "category": row.category,
                "total": round(cat_total, 2),
                "count": count,
                "avg_per_purchase": round(cat_total / count, 2) if count else 0.0,
                "pct_of_total": round(cat_total / total * 100, 1) if total else 0.0,
            }
        )
    return result
