"""Per-item price history/trend analysis, ported from price_tracker.py.

Dropped: Plotly rendering. Kept: the price-change and shop-comparison math,
operating on price_per_unit when available (falls back to amount).

Trends are grouped by (item, unit, category), not item alone: price_per_unit
means a different thing per unit (price per kg vs. per litre vs. per count),
and the same item name can be logged under different categories, so mixing
either would compare unrelated numbers.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean, pstdev


def _price(e: dict) -> float:
    ppu = e.get("price_per_unit") or 0.0
    return float(ppu) if ppu else float(e.get("amount") or 0.0)


def _unit(e: dict) -> str:
    return str(e.get("unit") or "Count").strip() or "Count"


def _category(e: dict) -> str:
    return str(e.get("category") or "").strip()


def price_trends(expenses: list[dict]) -> list[dict]:
    """Price-change summary per (item, unit, category) triple, needs >= 2 purchases."""
    by_item: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for e in expenses:
        desc = str(e.get("description") or "").strip()
        if desc:
            by_item[(desc, _unit(e), _category(e))].append(e)

    results = []
    for (item, unit, category), rows in by_item.items():
        if len(rows) < 2:
            continue
        rows = sorted(rows, key=lambda e: e["date"])
        prices = [_price(e) for e in rows]
        first_price, last_price = prices[0], prices[-1]
        change = last_price - first_price
        change_pct = (change / first_price * 100) if first_price else 0.0
        recent_avg = mean(prices[-3:])
        old_avg = mean(prices[:3])
        trend = "Increasing" if recent_avg > old_avg else "Decreasing" if recent_avg < old_avg else "Stable"

        results.append({
            "item": item,
            "category": category,
            "unit": unit,
            "first_date": rows[0]["date"].isoformat() if hasattr(rows[0]["date"], "isoformat") else rows[0]["date"],
            "last_date": rows[-1]["date"].isoformat() if hasattr(rows[-1]["date"], "isoformat") else rows[-1]["date"],
            "first_price": round(first_price, 2),
            "last_price": round(last_price, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 1),
            "avg_price": round(mean(prices), 2),
            "min_price": round(min(prices), 2),
            "max_price": round(max(prices), 2),
            "volatility": round(pstdev(prices), 2) if len(prices) > 1 else 0.0,
            "trend": trend,
            "purchases": len(rows),
        })

    return sorted(results, key=lambda r: r["change_pct"], reverse=True)


def shop_comparison(expenses: list[dict], item: str, unit: str | None = None, category: str | None = None) -> list[dict]:
    """Compare average/min/max price of the same item (unit, category) across shops."""
    item_norm = item.strip().lower()
    matches = [e for e in expenses if str(e.get("description", "")).strip().lower() == item_norm]
    if unit is not None:
        matches = [e for e in matches if _unit(e) == unit]
    if category is not None:
        matches = [e for e in matches if _category(e) == category]
    if not matches:
        return []

    by_shop: dict[str, list[float]] = defaultdict(list)
    for e in matches:
        shop = str(e.get("shop") or "Unknown").strip() or "Unknown"
        by_shop[shop].append(_price(e))

    rows = [
        {
            "shop": shop,
            "avg_price": round(mean(prices), 2),
            "min_price": round(min(prices), 2),
            "max_price": round(max(prices), 2),
            "times_bought": len(prices),
        }
        for shop, prices in by_shop.items()
    ]
    return sorted(rows, key=lambda r: r["avg_price"])


def price_history(expenses: list[dict], item: str, unit: str | None = None, category: str | None = None) -> list[dict]:
    """Timeline of (date, price, shop) points for a single item (unit, category), oldest first."""
    item_norm = item.strip().lower()
    matches = [e for e in expenses if str(e.get("description", "")).strip().lower() == item_norm]
    if unit is not None:
        matches = [e for e in matches if _unit(e) == unit]
    if category is not None:
        matches = [e for e in matches if _category(e) == category]
    matches.sort(key=lambda e: e["date"])
    return [
        {
            "date": e["date"].isoformat() if hasattr(e["date"], "isoformat") else e["date"],
            "price": round(_price(e), 2),
            "shop": e.get("shop", ""),
        }
        for e in matches
    ]
