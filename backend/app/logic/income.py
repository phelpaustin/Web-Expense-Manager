"""Pure income logic, ported from the Streamlit app's income_manager.py.

Dropped: JsonStore persistence and the Streamlit UI. Kept: the derived views
(monthly totals, this-month, average, total). Income rows come in as plain
dicts, so this stays storage-agnostic.
"""
from __future__ import annotations

import pandas as pd


def _to_frame(income: list[dict]) -> pd.DataFrame:
    if not income:
        return pd.DataFrame(columns=["date", "amount"])
    df = pd.DataFrame(income)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"])


def monthly_totals(income: list[dict]) -> list[dict]:
    """Total income per month, sorted ascending."""
    df = _to_frame(income)
    if df.empty:
        return []
    df["month"] = df["date"].dt.to_period("M").astype(str)
    monthly = df.groupby("month")["amount"].sum().reset_index().sort_values("month")
    return [{"month": row.month, "total": round(float(row.amount), 2)} for row in monthly.itertuples()]


def income_for_month(income: list[dict], month: str | None = None) -> float:
    """Total income for a 'YYYY-MM' month (defaults to the current month)."""
    df = _to_frame(income)
    if df.empty:
        return 0.0
    target = pd.Period(month, "M") if month else pd.Timestamp.now().to_period("M")
    df["_ym"] = df["date"].dt.to_period("M")
    return round(float(df.loc[df["_ym"] == target, "amount"].sum()), 2)


def average_monthly_income(income: list[dict]) -> float:
    """Average income across the months that have any income recorded."""
    monthly = monthly_totals(income)
    if not monthly:
        return 0.0
    return round(sum(m["total"] for m in monthly) / len(monthly), 2)


def total_income(income: list[dict]) -> float:
    df = _to_frame(income)
    return round(float(df["amount"].sum()), 2) if not df.empty else 0.0


def summary(income: list[dict]) -> dict:
    return {
        "this_month": income_for_month(income),
        "avg_month": average_monthly_income(income),
        "total": total_income(income),
        "count": len(income),
    }
