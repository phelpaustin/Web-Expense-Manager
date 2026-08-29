"""Trip expense summary — aggregates expenses tagged with a trip_id."""
from __future__ import annotations

from collections import defaultdict


def trip_summary(trip: dict, expenses: list[dict]) -> dict:
    total_spent = round(sum(float(e.get("amount") or 0.0) for e in expenses), 2)
    by_category: dict[str, float] = defaultdict(float)
    for e in expenses:
        by_category[e.get("category") or "Uncategorized"] += float(e.get("amount") or 0.0)

    budget = trip.get("budget")
    remaining = (budget - total_spent) if budget else None

    return {
        "trip_id": trip["id"],
        "total_spent": total_spent,
        "budget": budget,
        "remaining": round(remaining, 2) if remaining is not None else None,
        "expense_count": len(expenses),
        "by_category": {k: round(v, 2) for k, v in sorted(by_category.items(), key=lambda kv: -kv[1])},
    }


def trip_settlement(members: list[dict], expenses: list[dict]) -> dict:
    """Who paid what vs. their equal share, and the minimal set of payments to settle up.

    members: [{"user_id", "name", "email"}, ...] — everyone splitting the trip cost.
    expenses: [{"user_id", "amount"}, ...] — who actually paid for each expense.
    """
    total_spent = round(sum(float(e.get("amount") or 0.0) for e in expenses), 2)
    member_count = len(members) or 1
    share = round(total_spent / member_count, 2)

    paid_by: dict[int, float] = defaultdict(float)
    for e in expenses:
        paid_by[e.get("user_id")] += float(e.get("amount") or 0.0)

    per_member = []
    for m in members:
        paid = round(paid_by.get(m["user_id"], 0.0), 2)
        per_member.append({
            "user_id": m["user_id"],
            "name": m.get("name") or m.get("email") or "",
            "email": m.get("email", ""),
            "paid": paid,
            "share": share,
            "balance": round(paid - share, 2),
        })

    # Greedily match the biggest debtor with the biggest creditor to minimise the
    # number of payments needed to settle everyone up.
    debtors = sorted([dict(m) for m in per_member if m["balance"] < -0.01], key=lambda m: m["balance"])
    creditors = sorted([dict(m) for m in per_member if m["balance"] > 0.01], key=lambda m: -m["balance"])
    transactions = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debtor, creditor = debtors[i], creditors[j]
        amount = round(min(-debtor["balance"], creditor["balance"]), 2)
        if amount > 0.01:
            transactions.append({
                "from_user_id": debtor["user_id"],
                "from_name": debtor["name"],
                "to_user_id": creditor["user_id"],
                "to_name": creditor["name"],
                "amount": amount,
            })
        debtor["balance"] = round(debtor["balance"] + amount, 2)
        creditor["balance"] = round(creditor["balance"] - amount, 2)
        if abs(debtor["balance"]) < 0.01:
            i += 1
        if abs(creditor["balance"]) < 0.01:
            j += 1

    return {
        "total_spent": total_spent,
        "share_per_person": share,
        "per_member": per_member,
        "transactions": transactions,
    }
