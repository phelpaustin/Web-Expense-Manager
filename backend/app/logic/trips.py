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
