"""Shop scorecard: where the money goes, and which shops are cheap for what you buy.

Per shop over a period: spend, share of spend, visits, spend per visit, and a price index
that says whether the shop is dearer or cheaper than the others for the same things.

The price index
  Only things bought at two or more shops can be compared, and only like with like: the
  same item name, brand, category and kind of unit (prices are per Kg, Litre, ... so 500 g
  and 5 kg compare). For each such item every shop gets its average unit price, and the
  item's reference price is the mean of those shop averages. A shop's index is its prices
  relative to that reference, averaged over the items it sells weighted by how much you
  spend on each there. 100 is the average shop; 92 is 8% cheaper than that.

  Needs at least MIN_ITEMS_FOR_INDEX shared items. It describes the items you actually buy
  at several shops, not the shop's whole range, and ignores travel time and quality.
  Purchases with no shop recorded count towards spend but can't be compared.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

import pandas as pd

from app.core.money import as_decimal, quantize_money
from app.logic.category_change import _as_date
from app.logic.names import clean_name, name_key
from app.logic.price_tracker import _category, _most_used_spelling, _unit
from app.logic.units import normalise_unit, to_base_price

MIN_ITEMS_FOR_INDEX = 3
DEFAULT_MONTHS = 6
MAX_OPPORTUNITIES = 5
UNKNOWN_SHOP = "Unknown"
_DAYS_PER_MONTH = 30.4375
_ZERO = quantize_money(0)


def window_start(today: date, months: int) -> date | None:
    """First day of a period reaching back `months` months from today; None for all time."""
    if months <= 0:
        return None
    return (pd.Timestamp(today) - pd.DateOffset(months=months)).date()


def with_bill_shops(expenses: list[dict]) -> list[dict]:
    """Copies of the expenses in which a bill's recorded total names its shop.

    Recording a bill as a total stores the shop in the expense's description and leaves its
    shop empty, so without this the biggest shop spending would all read as "no shop".
    Rows that already have a shop, and ordinary expenses, are returned unchanged.
    """
    out = []
    for e in expenses:
        if e.get("bill_total_only") and not clean_name(e.get("shop")) and clean_name(e.get("description")):
            e = {**e, "shop": e["description"]}
        out.append(e)
    return out


def _unit_price(e: dict) -> Decimal:
    """Price per base unit (Kg, Litre, ...), unrounded so cheap items keep their precision."""
    ppu = e.get("price_per_unit")
    return to_base_price(ppu if ppu else e.get("amount"), e.get("unit"))


def _base_quantity(e: dict) -> Decimal:
    """How much was bought, in base units (500 g is 0.5 Kg)."""
    return as_decimal(e.get("quantity") or 1) * normalise_unit(e.get("unit")).factor


def _pct(numerator: Decimal, denominator: Decimal, places: int = 1) -> float | None:
    return round(float(numerator / denominator * 100), places) if denominator else None


def shop_scorecard(expenses: list[dict], today: date | None = None, months: int = DEFAULT_MONTHS) -> dict:
    today = today or date.today()
    start = window_start(today, months)
    expenses = with_bill_shops(expenses)

    dated = [(d, e) for e in expenses if (d := _as_date(e.get("date"))) is not None and d <= today]
    in_window = [(d, e) for d, e in dated if start is None or d >= start]

    shops: dict[str, dict] = {}
    items: dict[tuple, dict] = {}
    unknown_spend, unknown_purchases = _ZERO, 0

    for d, e in in_window:
        amount = as_decimal(e.get("amount"))
        label = clean_name(e.get("shop"))
        if not label:
            unknown_spend += amount
            unknown_purchases += 1
            continue
        key = name_key(label)
        shop = shops.setdefault(key, {"labels": Counter(), "spend": Decimal(0), "purchases": 0, "dates": set()})
        shop["labels"][label] += 1
        shop["spend"] += amount
        shop["purchases"] += 1
        shop["dates"].add(d)

        # A bill's total with no items says nothing about any item's price.
        description = clean_name(e.get("description"))
        if e.get("bill_total_only") or not description:
            continue
        price = _unit_price(e)
        if price <= 0:
            continue
        item = items.setdefault(
            (name_key(description), _unit(e), _category(e), name_key(e.get("brand"))),
            {"names": [], "brand": clean_name(e.get("brand")), "shops": {}},
        )
        item["names"].append(description)
        at_shop = item["shops"].setdefault(key, {"prices": [], "quantity": Decimal(0), "spend": Decimal(0)})
        at_shop["prices"].append(price)
        at_shop["quantity"] += _base_quantity(e)
        at_shop["spend"] += amount

    # --- price comparison across shops -------------------------------------------------
    stats = {k: {"weighted": Decimal(0), "weight": Decimal(0), "items": 0, "cheapest": 0, "saving": Decimal(0)} for k in shops}
    opportunities = []
    for (_, unit, category, _), item in items.items():
        if len(item["shops"]) < 2:
            continue
        averages = {k: sum(v["prices"]) / len(v["prices"]) for k, v in item["shops"].items()}
        reference = sum(averages.values()) / len(averages)
        cheapest = min(averages.values())
        cheapest_shops = [k for k, avg in averages.items() if avg == cheapest]
        has_a_cheaper_shop = len(cheapest_shops) < len(averages)
        name = _most_used_spelling(item["names"])

        for k, avg in averages.items():
            s = stats[k]
            weight = item["shops"][k]["spend"]
            s["weighted"] += weight * (avg / reference)
            s["weight"] += weight
            s["items"] += 1
            if has_a_cheaper_shop and k in cheapest_shops:
                s["cheapest"] += 1
            if avg > cheapest:
                saving = (avg - cheapest) * item["shops"][k]["quantity"]
                s["saving"] += saving
                cheaper = min(cheapest_shops, key=lambda c: shops[c]["labels"].most_common(1)[0][0].casefold())
                opportunities.append({
                    "item": name,
                    "brand": item["brand"],
                    "unit": unit,
                    "category": category,
                    "shop": _label(shops[k]),
                    "price": quantize_money(avg),
                    "cheaper_shop": _label(shops[cheaper]),
                    "cheaper_price": quantize_money(cheapest),
                    "pay_more_pct": _pct(avg - cheapest, cheapest),
                    "saving": quantize_money(saving),
                })

    opportunities = [o for o in opportunities if o["saving"] > 0]
    opportunities.sort(key=lambda o: (-o["saving"], o["item"].casefold(), o["shop"].casefold()))

    # --- per-shop rows ---------------------------------------------------------------------
    named_spend = quantize_money(sum((v["spend"] for v in shops.values()), Decimal(0)))
    first_any = min((d for d, _ in dated), default=None)
    effective_start = max(filter(None, [start, first_any]), default=today)
    span_months = max(1.0, (today - effective_start).days / _DAYS_PER_MONTH)

    rows = []
    for key, shop in shops.items():
        s, spend, visits = stats[key], quantize_money(shop["spend"]), len(shop["dates"])
        enough = s["items"] >= MIN_ITEMS_FOR_INDEX and s["weight"] > 0
        rows.append({
            "shop": _label(shop),
            "spend": spend,
            "share_pct": _pct(shop["spend"], named_spend),
            "purchases": shop["purchases"],
            "visits": visits,
            "visits_per_month": round(visits / span_months, 1),
            "avg_visit": quantize_money(shop["spend"] / visits),
            "first_visit": min(shop["dates"]).isoformat(),
            "last_visit": max(shop["dates"]).isoformat(),
            "price_index": round(float(s["weighted"] / s["weight"] * 100), 1) if enough else None,
            "items_compared": s["items"],
            "cheapest_on": s["cheapest"],
            "coverage_pct": _pct(s["weight"], shop["spend"]) if s["items"] else None,
            "potential_saving": quantize_money(s["saving"]),
        })
    rows.sort(key=lambda r: (-r["spend"], r["shop"].casefold()))

    return {
        "period": {
            "months": months,
            "from": (start or effective_start).isoformat() if (start or first_any) else None,
            "to": today.isoformat(),
        },
        "available": bool(rows),
        "named_spend": named_spend,
        "unknown": {"spend": quantize_money(unknown_spend), "purchases": unknown_purchases},
        "shops": rows,
        "opportunities": opportunities[:MAX_OPPORTUNITIES],
        "min_items_for_index": MIN_ITEMS_FOR_INDEX,
    }


def _label(shop: dict) -> str:
    """The shop's name as shown: the spelling used most, alphabetical on a tie."""
    counts = shop["labels"]
    return min(counts, key=lambda s: (-counts[s], s))
