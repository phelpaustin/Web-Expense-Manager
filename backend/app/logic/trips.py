"""Trip expense summary — aggregates expenses tagged with a trip_id."""
from __future__ import annotations

from collections import defaultdict
from app.core.money import quantize_money


def trip_summary(trip: dict, expenses: list[dict]) -> dict:
    total_spent = quantize_money(sum((quantize_money(e.get("amount")) for e in expenses), quantize_money(0)))
    by_category: dict[str, object] = defaultdict(lambda: quantize_money(0))
    for e in expenses:
        by_category[e.get("category") or "Uncategorized"] += quantize_money(e.get("amount"))

    budget = trip.get("budget")
    remaining = (budget - total_spent) if budget else None

    return {
        "trip_id": trip["id"],
        "currency": trip.get("currency") or "SEK",
        "total_spent": total_spent,
        "budget": budget,
        "remaining": quantize_money(remaining) if remaining is not None else None,
        "expense_count": len(expenses),
        "by_category": {k: quantize_money(v) for k, v in sorted(by_category.items(), key=lambda kv: -kv[1])},
    }


def trip_settlement(members: list[dict], expenses: list[dict], currency: str = "SEK") -> dict:
    """Who paid what vs. their equal share, and the minimal set of payments to settle up.

    members: [{"user_id", "name", "email"}, ...] — everyone splitting the trip cost.
    expenses: [{"user_id", "amount"}, ...] — who actually paid for each expense.
    """
    total_spent = quantize_money(sum((quantize_money(e.get("amount")) for e in expenses), quantize_money(0)))
    member_count = len(members) or 1
    share = quantize_money(total_spent / member_count)

    paid_by: dict[int, object] = defaultdict(lambda: quantize_money(0))
    for e in expenses:
        paid_by[e.get("user_id")] += quantize_money(e.get("amount"))

    per_member = []
    for m in members:
        paid = quantize_money(paid_by.get(m["user_id"], 0))
        per_member.append({
            "user_id": m["user_id"],
            "name": m.get("name") or m.get("email") or "",
            "email": m.get("email", ""),
            "paid": paid,
            "share": share,
            "balance": quantize_money(paid - share),
        })

    # Greedily match the biggest debtor with the biggest creditor to minimise the
    # number of payments needed to settle everyone up.
    debtors = sorted([dict(m) for m in per_member if m["balance"] < -0.01], key=lambda m: m["balance"])
    creditors = sorted([dict(m) for m in per_member if m["balance"] > 0.01], key=lambda m: -m["balance"])
    transactions = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debtor, creditor = debtors[i], creditors[j]
        amount = quantize_money(min(-debtor["balance"], creditor["balance"]))
        if amount > 0.01:
            transactions.append({
                "from_user_id": debtor["user_id"],
                "from_name": debtor["name"],
                "to_user_id": creditor["user_id"],
                "to_name": creditor["name"],
                "amount": amount,
            })
        debtor["balance"] = quantize_money(debtor["balance"] + amount)
        creditor["balance"] = quantize_money(creditor["balance"] - amount)
        if abs(debtor["balance"]) < quantize_money("0.01"):
            i += 1
        if abs(creditor["balance"]) < quantize_money("0.01"):
            j += 1

    return {
        "currency": currency or "SEK",
        "total_spent": total_spent,
        "share_per_person": share,
        "per_member": per_member,
        "transactions": transactions,
    }
