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
