"""Pure bills-ledger projection, ported from bills_ledger.py.

The ledger is a read-only, de-duplicated view over three sources:
itemised expenses (collapsed per date+label), pending bills, and manual
bills. Duplicates across sources are removed by a (date, label, amount) key,
keeping the richest source first: Expense > Pending > Manual.

Storage and Streamlit UI are dropped; rows come in as plain dicts. Because
the new expense schema has no "shop" field, the expense's `description` is
used as the ledger label.
"""
from __future__ import annotations

import io

import pandas as pd

SOURCE_EXPENSE = "Expense"
SOURCE_PENDING = "Pending"
SOURCE_MANUAL = "Manual"

_SOURCE_PRIORITY = {SOURCE_EXPENSE: 0, SOURCE_PENDING: 1, SOURCE_MANUAL: 2}


def _key(date, label, amount) -> tuple[str, str, float]:
    try:
        amt = round(float(amount or 0.0), 2)
    except (TypeError, ValueError):
        amt = 0.0
    return (str(date), str(label or "").strip().lower(), amt)


def build_ledger(expenses: list[dict], pending: list[dict], manual: list[dict]) -> list[dict]:
    """Return the consolidated, de-duplicated ledger, newest first."""
    rows: list[dict] = []

    # Collapse itemised expenses into one bill total per (date, shop/label).
    groups: dict[tuple[str, str], float] = {}
    for e in expenses:
        label = (e.get("shop") or e.get("description") or "").strip()
        gkey = (str(e["date"]), label)
        groups[gkey] = groups.get(gkey, 0.0) + float(e.get("amount") or 0.0)
    for (date_str, label), amount in groups.items():
        rows.append(
            {"date": date_str, "shop": label, "amount": round(amount, 2), "source": SOURCE_EXPENSE, "id": None}
        )

    for p in pending:
        rows.append(
            {"date": str(p["date"]), "shop": p.get("shop", ""), "amount": round(float(p["amount"]), 2),
             "source": SOURCE_PENDING, "id": p.get("id")}
        )
    for m in manual:
        rows.append(
            {"date": str(m["date"]), "shop": m.get("shop", ""), "amount": round(float(m["amount"]), 2),
             "source": SOURCE_MANUAL, "id": m.get("id")}
        )

    # De-duplicate keeping the highest-priority source.
    rows.sort(key=lambda r: _SOURCE_PRIORITY.get(r["source"], 9))
    seen: set[tuple[str, str, float]] = set()
    unique: list[dict] = []
    for r in rows:
        k = _key(r["date"], r["shop"], r["amount"])
        if k in seen:
            continue
        seen.add(k)
        unique.append(r)

    unique.sort(key=lambda r: r["date"], reverse=True)
    return unique


# ═══════════════════════════════════════════════════════════════
# BULK IMPORT (bank statement spreadsheet → pending bills)
# ═══════════════════════════════════════════════════════════════
_DATE_HEADERS = {"date", "transaction date", "posted date", "posting date", "value date"}
_SHOP_HEADERS = {"shop", "merchant", "description", "payee", "narrative", "details", "name"}
_AMOUNT_HEADERS = {"amount", "debit", "withdrawal", "value", "transaction amount"}


def _find_column(columns, candidates: set[str]) -> str | None:
    lower = {str(c).strip().lower(): c for c in columns}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    return None


def parse_bill_rows(data: bytes, filename: str) -> tuple[list[dict], list[dict]]:
    """Parse an uploaded bank-statement spreadsheet (date, shop, amount columns).

    Returns (rows, skipped): rows are {"date": date, "shop": str, "amount": float}
    (positive, rounded to 2 decimals); skipped is [{"row": <1-based, header excluded>,
    "reason": str}] for rows that couldn't be parsed.
    """
    buf = io.BytesIO(data)
    if (filename or "").lower().endswith(".csv"):
        df = pd.read_csv(buf)
    else:
        df = pd.read_excel(buf)

    date_col = _find_column(df.columns, _DATE_HEADERS)
    shop_col = _find_column(df.columns, _SHOP_HEADERS)
    amount_col = _find_column(df.columns, _AMOUNT_HEADERS)
    if not date_col or not shop_col or not amount_col:
        raise ValueError(
            "Could not find date/shop/amount columns. Expected headers such as "
            "'Date', 'Shop' (or 'Description'/'Merchant'), and 'Amount'."
        )

    rows: list[dict] = []
    skipped: list[dict] = []
    for i, raw in enumerate(df.to_dict("records"), start=2):  # row 1 is the header
        try:
            date_val = pd.to_datetime(raw[date_col]).date()
            shop_val = str(raw[shop_col]).strip()
            amount_val = abs(float(raw[amount_col]))
            if not shop_val or shop_val.lower() == "nan":
                raise ValueError("missing shop name")
            if not amount_val:
                raise ValueError("missing or zero amount")
        except Exception as exc:  # noqa: BLE001 – any parse issue just skips the row
            skipped.append({"row": i, "reason": str(exc)})
            continue
        rows.append({"date": date_val, "shop": shop_val, "amount": round(amount_val, 2)})
    return rows, skipped


def flag_duplicates(rows: list[dict], existing: list[tuple]) -> None:
    """Mark rows (in place, adds "possible_duplicate") whose (date, amount) matches
    an existing expense or pending bill. The shop name is deliberately ignored —
    bank statement wording rarely matches what was typed in by hand — so these are
    flagged for the user to manually verify and delete if they're truly duplicates.
    """
    existing_keys = {(str(d), round(float(a), 2)) for d, a in existing}
    for row in rows:
        row["possible_duplicate"] = (str(row["date"]), row["amount"]) in existing_keys
