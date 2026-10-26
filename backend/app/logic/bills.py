"""Parsing a bank-statement spreadsheet into bill rows (date, shop, amount).

The older bulk-upload route still uses this; the Import page has its own, richer parser.
"""
from __future__ import annotations

import io

import pandas as pd

from app.core.file_upload import ensure_xlsx_within_limits
from app.core.money import quantize_money
from app.core.parsing import parse_amount, read_csv_bytes, unescape_formula
from app.core.import_limits import MAX_IMPORT_ROWS

# ═══════════════════════════════════════════════════════════════
# BULK IMPORT (bank statement spreadsheet → pending bills)
# ═══════════════════════════════════════════════════════════════
# Header names, in order of preference. These are tuples (not sets) on purpose:
# when a statement has several candidate columns the choice must be the same on
# every run, never dependent on hash/iteration order.
_DATE_HEADERS = (
    "date", "transaction date", "posting date", "posted date", "booking date", "value date",
    "datum", "transaktionsdatum", "bokföringsdatum",
)
_SHOP_HEADERS = (
    "shop", "merchant", "description", "payee", "narrative", "details", "name",
    "text", "beskrivning", "mottagare",
)
# A signed "amount" column mixes money out (negative) and money in (positive);
# a "debit"-style column only ever holds money out.
_SIGNED_AMOUNT_HEADERS = ("amount", "transaction amount", "belopp", "value")
_OUTFLOW_AMOUNT_HEADERS = ("debit", "withdrawal", "withdrawals", "paid out", "money out")


def _find_column(columns, candidates) -> str | None:
    lower = {str(c).strip().lower(): c for c in columns}
    for cand in candidates:  # candidates is ordered: first match wins, deterministically
        if cand in lower:
            return lower[cand]
    return None


def parse_bill_rows(data: bytes, filename: str) -> tuple[list[dict], list[dict]]:
    """Parse an uploaded bank-statement spreadsheet (date, shop, amount columns).

    Returns (rows, skipped): rows are {"date": date, "shop": str, "amount": Decimal}
    (positive, rounded to 2 decimals); skipped is [{"row": <1-based, header excluded>,
    "reason": str}] for rows that couldn't be used.

    Only money going *out* becomes a bill. With a debit/withdrawal column every
    value is an outflow. With a signed amount column that contains negatives,
    negatives are outflows and positives (salary, refunds, deposits) are skipped
    as credits. A signed column with no negatives at all is treated as an
    expenses-only export, so all its rows are bills.
    """
    name = (filename or "").lower()
    if name.endswith(".csv"):
        df = read_csv_bytes(data, nrows=MAX_IMPORT_ROWS + 1)
    elif name.endswith(".xlsx"):
        ensure_xlsx_within_limits(data)
        df = pd.read_excel(io.BytesIO(data), nrows=MAX_IMPORT_ROWS + 1)
    else:
        raise ValueError("Only .xlsx or .csv files are allowed")

    if len(df.index) > MAX_IMPORT_ROWS:
        raise ValueError(f"File has more than {MAX_IMPORT_ROWS:,} data rows")

    date_col = _find_column(df.columns, _DATE_HEADERS)
    shop_col = _find_column(df.columns, _SHOP_HEADERS)
    signed_col = _find_column(df.columns, _SIGNED_AMOUNT_HEADERS)
    outflow_col = _find_column(df.columns, _OUTFLOW_AMOUNT_HEADERS)
    amount_col = signed_col or outflow_col
    if not date_col or not shop_col or not amount_col:
        raise ValueError(
            "Could not find date/shop/amount columns. Expected headers such as "
            "'Date', 'Shop' (or 'Description'/'Merchant'), and 'Amount'."
        )
    outflow_only = signed_col is None  # a debit-style column: every value is money out

    parsed: list[tuple[int, dict]] = []
    skipped: list[dict] = []
    for i, raw in enumerate(df.to_dict("records"), start=2):  # row 1 is the header
        try:
            date_val = pd.to_datetime(raw[date_col]).date()
            shop_val = str(unescape_formula(raw[shop_col])).strip()
            if not shop_val or shop_val.lower() == "nan":
                raise ValueError("missing shop name")
            amount_val = quantize_money(parse_amount(raw[amount_col]))
            if not amount_val:
                raise ValueError("missing or zero amount")
        except (ValueError, TypeError, ArithmeticError) as exc:
            skipped.append({"row": i, "reason": str(exc)})
            continue
        parsed.append((i, {"date": date_val, "shop": shop_val, "amount": amount_val}))

    has_negatives = any(r["amount"] < 0 for _, r in parsed)
    rows: list[dict] = []
    for i, r in parsed:
        if not outflow_only and has_negatives and r["amount"] > 0:
            skipped.append({"row": i, "reason": "Credit / deposit (money in), not an expense"})
            continue
        rows.append({**r, "amount": abs(r["amount"])})
    skipped.sort(key=lambda s: s["row"])
    return rows, skipped


def flag_duplicates(rows: list[dict], existing: list[tuple]) -> None:
    """Mark rows (in place, adds "possible_duplicate") whose (date, amount) matches
    an existing expense or pending bill. The shop name is deliberately ignored —
    bank statement wording rarely matches what was typed in by hand — so these are
    flagged for the user to manually verify and delete if they're truly duplicates.
    """
    existing_keys = {(str(d), quantize_money(a)) for d, a in existing}
    for row in rows:
        row["possible_duplicate"] = (str(row["date"]), row["amount"]) in existing_keys
