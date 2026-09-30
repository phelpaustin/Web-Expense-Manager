"""Pure income logic, ported from the Streamlit app's income_manager.py.

Dropped: JsonStore persistence and the Streamlit UI. Kept: the derived views
(monthly totals, this-month, average, total). Income rows come in as plain
dicts, so this stays storage-agnostic.
"""
from __future__ import annotations

import pandas as pd

from app.core.money import as_decimal, quantize_money


def _to_frame(income: list[dict]) -> pd.DataFrame:
    if not income:
        return pd.DataFrame(columns=["date", "amount"])
    df = pd.DataFrame(income)
    df["amount"] = df["amount"].map(lambda value: as_decimal(value) if not pd.isna(value) else as_decimal(0))
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"])


def monthly_totals(income: list[dict]) -> list[dict]:
    """Total income per month, sorted ascending."""
    df = _to_frame(income)
    if df.empty:
        return []
    df["month"] = df["date"].dt.to_period("M").astype(str)
    monthly = df.groupby("month")["amount"].sum().reset_index().sort_values("month")
    return [{"month": row.month, "total": quantize_money(row.amount)} for row in monthly.itertuples()]


def income_for_month(income: list[dict], month: str | None = None) -> float:
    """Total income for a 'YYYY-MM' month (defaults to the current month)."""
    df = _to_frame(income)
    if df.empty:
        return quantize_money(0)
    target = pd.Period(month, "M") if month else pd.Timestamp.now().to_period("M")
    df["_ym"] = df["date"].dt.to_period("M")
    return quantize_money(df.loc[df["_ym"] == target, "amount"].sum())


def average_monthly_income(income: list[dict]) -> float:
    """Average income across the months that have any income recorded."""
    monthly = monthly_totals(income)
    if not monthly:
        return quantize_money(0)
    return quantize_money(sum(m["total"] for m in monthly) / len(monthly))


def total_income(income: list[dict]) -> float:
    df = _to_frame(income)
    return quantize_money(df["amount"].sum()) if not df.empty else quantize_money(0)


def summary(income: list[dict]) -> dict:
    return {
        "this_month": income_for_month(income),
        "avg_month": average_monthly_income(income),
        "total": total_income(income),
        "count": len(income),
    }
