"""Shared helpers for building the small DataFrames the aggregations run on."""
from __future__ import annotations

from decimal import Decimal

import pandas as pd

from app.core.money import as_decimal

_ZERO = Decimal("0")


def decimal_amounts(values) -> pd.Series:
    """Amounts as exact Decimals (missing/NaN -> 0), without a per-value pandas round trip."""
    return pd.Series(
        [v if isinstance(v, Decimal) else (_ZERO if pd.isna(v) else as_decimal(v)) for v in values],
        dtype=object,
    )


def frame(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    """Only the columns an aggregation reads. Converted expenses carry a dozen more keys
    (original amount/currency, unit price, shop, ...); copying them into the frame for every
    calculation was a large share of the dashboard's time."""
    df = pd.DataFrame(rows, columns=columns)
    df["amount"] = decimal_amounts(df["amount"]).set_axis(df.index)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df
