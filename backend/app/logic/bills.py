"""Pure bills-ledger projection, ported from bills_ledger.py.

The ledger is a read-only, de-duplicated view over three sources:
itemised expenses (collapsed per date+label), pending bills, and manual
bills. Duplicates across sources are removed by a (date, label, amount, currency) key,
keeping the richest source first: Expense > Pending > Manual.

Storage and Streamlit UI are dropped; rows come in as plain dicts. Because
the new expense schema has no "shop" field, the expense's `description` is
used as the ledger label.
"""
from __future__ import annotations

import io

import pandas as pd

from app.core.money import quantize_money
from app.core.parsing import parse_amount, read_csv_bytes
from app.core.import_limits import MAX_IMPORT_ROWS

SOURCE_EXPENSE = "Expense"
SOURCE_PENDING = "Pending"
SOURCE_MANUAL = "Manual"

_SOURCE_PRIORITY = {SOURCE_EXPENSE: 0, SOURCE_PENDING: 1, SOURCE_MANUAL: 2}


def _key(date, label, amount, currency) -> tuple[str, str, object, str]:
    try:
        amt = quantize_money(amount)
    except (TypeError, ValueError):
        amt = quantize_money(0)
    return (
        str(date),
        str(label or "").strip().lower(),
        amt,
        str(currency or "SEK").upper(),
    )


def build_ledger(
    expenses: list[dict], pending: list[dict], manual: list[dict], base_currency: str = "SEK"
) -> list[dict]:
    """Return the consolidated, de-duplicated ledger, newest first."""
    rows: list[dict] = []

    # Collapse itemised expenses by date, label, and currency so raw values
    # from different currencies can never be added together.
    groups: dict[tuple[str, str, str], object] = {}
    for e in expenses:
        label = (e.get("shop") or e.get("description") or "").strip()
        currency = str(e.get("currency") or base_currency).upper()
        gkey = (str(e["date"]), label, currency)
        groups[gkey] = groups.get(gkey, quantize_money(0)) + quantize_money(e.get("amount"))
    for (date_str, label, currency), amount in groups.items():
        rows.append(
            {
                "date": date_str,
                "shop": label,
                "amount": quantize_money(amount),
                "currency": currency,
                "source": SOURCE_EXPENSE,
                "id": None,
            }
        )

    for p in pending:
        rows.append(
            {
                "date": str(p["date"]),
                "shop": p.get("shop", ""),
                "amount": quantize_money(p["amount"]),
                "currency": str(p.get("currency") or base_currency).upper(),
                "source": SOURCE_PENDING,
                "id": p.get("id"),
            }
        )
    for m in manual:
        rows.append(
            {
                "date": str(m["date"]),
                "shop": m.get("shop", ""),
                "amount": quantize_money(m["amount"]),
                "currency": str(m.get("currency") or base_currency).upper(),
                "source": SOURCE_MANUAL,
                "id": m.get("id"),
            }
        )

    # De-duplicate keeping the highest-priority source.
    rows.sort(key=lambda r: _SOURCE_PRIORITY.get(r["source"], 9))
    seen: set[tuple[str, str, object, str]] = set()
    unique: list[dict] = []
    for r in rows:
        k = _key(r["date"], r["shop"], r["amount"], r["currency"])
        if k in seen:
            continue
        seen.add(k)
        unique.append(r)

    unique.sort(key=lambda r: r["date"], reverse=True)
    return unique


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
            shop_val = str(raw[shop_col]).strip()
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
