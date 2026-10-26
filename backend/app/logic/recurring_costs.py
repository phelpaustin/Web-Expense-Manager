"""What do my recurring payments add up to?

"Eleven recurring payments, about 3,400 SEK a month (40,800 a year). Netflix went up 20% in
September." Every recurring template is turned into a cost per month and per year, with its next
due date, and a price rise is spotted when the amount it posted last differs from what it posted
before. Pure functions on plain dicts.

Amounts are compared in the template's own currency, so a change in exchange rate is never
mistaken for a price rise.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.money import as_decimal, quantize_money
from app.logic.recurring import next_due

# Payments in a year, by frequency. An unknown frequency counts as monthly, as the schedule does.
PER_YEAR = {
    "Daily": Decimal(365),
    "Weekly": Decimal(52),
    "Bi-weekly": Decimal(26),
    "Monthly": Decimal(12),
    "Quarterly": Decimal(4),
    "Yearly": Decimal(1),
}


def yearly_cost(amount, frequency: str) -> Decimal:
    return quantize_money(as_decimal(amount) * PER_YEAR.get(frequency, Decimal(12)))


def monthly_cost(amount, frequency: str) -> Decimal:
    return quantize_money(as_decimal(amount) * PER_YEAR.get(frequency, Decimal(12)) / 12)


def price_change(payments: list[dict]) -> dict | None:
    """A rise or fall in what a template posted, from its payments (oldest to newest by date).

    Looks at the newest payment and the latest earlier one for a different amount, in the same
    currency. Returns None when the amount has never changed (or there is only one payment).
    """
    if not payments:
        return None
    ordered = sorted(payments, key=lambda p: (p["date"], p.get("id") or 0))
    latest = ordered[-1]
    same = [p for p in ordered if p.get("currency") == latest.get("currency")]
    now = as_decimal(latest["amount"])
    for i in range(len(same) - 2, -1, -1):
        before = as_decimal(same[i]["amount"])
        if before != now:
            change = now - before
            return {
                "from": quantize_money(before),
                "to": quantize_money(now),
                "since": same[i + 1]["date"],
                "currency": latest.get("currency"),
                "pct_change": round(float(change / before * 100), 1) if before else None,
                "direction": "up" if change > 0 else "down",
            }
    return None


def recurring_costs(templates: list[dict], payments: list[dict], today: date | None = None) -> dict:
    """Cost per month and per year of each template, and in total.

    `templates` carry `amount` already converted to the reporting currency (what the totals are
    added up in), plus their own `native_amount` and `native_currency`. `payments` are the
    expenses the templates posted: `template_id`, `date`, `amount`, `currency` in their own currency.
    """
    today = today or date.today()
    by_template: dict[int, list[dict]] = {}
    for p in payments:
        by_template.setdefault(p["template_id"], []).append(p)

    items = []
    for t in templates:
        paid = by_template.get(t["id"], [])
        due = next_due(t.get("last_applied"), t["frequency"], today, t.get("schedule_anchor"))
        items.append({
            "id": t["id"],
            "item": t["item"],
            "category": t.get("category") or "",
            "frequency": t["frequency"],
            "amount": quantize_money(t["amount"]),
            "native_amount": quantize_money(t["native_amount"]),
            "native_currency": t["native_currency"],
            "monthly": monthly_cost(t["amount"], t["frequency"]),
            "yearly": yearly_cost(t["amount"], t["frequency"]),
            "next_due": due,
            "overdue": due < today,
            "last_paid": max((p["date"] for p in paid), default=None),
            "payments": len(paid),
            "price_change": price_change(paid),
        })
    items.sort(key=lambda i: (-i["monthly"], i["item"].lower(), i["id"]))
    return {
        "count": len(items),
        "monthly_total": sum((i["monthly"] for i in items), quantize_money(0)),
        "yearly_total": sum((i["yearly"] for i in items), quantize_money(0)),
        "price_rises": sum(1 for i in items if i["price_change"] and i["price_change"]["direction"] == "up"),
        "items": items,
    }


__all__ = ["recurring_costs", "price_change", "monthly_cost", "yearly_cost"]
