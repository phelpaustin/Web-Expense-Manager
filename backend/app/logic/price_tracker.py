"""Per-item price history/trend analysis, ported from price_tracker.py.

Dropped: Plotly rendering. Kept: the price-change and shop-comparison math,
operating on price_per_unit when available (falls back to amount).

Trends are grouped by (item, unit kind, category), not item alone: price_per_unit
means a different thing per unit (price per kg vs. per litre vs. per count),
and the same item name can be logged under different categories, so mixing
either would compare unrelated numbers.

Units of the same kind are compared together: every price is restated per base unit
(Kg, Litre, Meter, Count; see app.logic.units), so 0.02 per g and 20 per kg are one
price. Item names match ignoring case and spacing (see app.logic.names); callers that
also apply the user's aliases do so first, with names.canonicalise().
"""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean, pstdev

from app.core.money import quantize_money
from app.logic.names import clean_name, name_key
from app.logic.units import to_base_price, unit_label


def _price(e: dict):
    """The price per base unit (per Kg, per Litre, ...), falling back to the amount."""
    ppu = e.get("price_per_unit")
    return quantize_money(to_base_price(ppu if ppu else e.get("amount"), e.get("unit")))


def _unit(e: dict) -> str:
    """The unit rows are compared in: the base unit of whatever was logged."""
    return unit_label(e.get("unit"))


def _category(e: dict) -> str:
    return str(e.get("category") or "").strip()


def _shop_label(e: dict) -> str:
    """The shop as shown; purchases with no shop are grouped as "Unknown"."""
    return clean_name(e.get("shop")) or "Unknown"


def _matching(
    expenses: list[dict],
    item: str,
    unit: str | None,
    category: str | None,
    brand: str | None = None,
    shops: list[str] | None = None,
) -> list[dict]:
    """The purchases of one item, optionally narrowed to a brand and/or some shops.

    Names are compared ignoring case and spacing. `brand=None` means every brand and
    `brand=""` means purchases with no brand recorded. `shops=None` means every shop;
    a list keeps only those shops ("Unknown" stands for purchases with no shop).
    """
    wanted = name_key(item)
    matches = [e for e in expenses if name_key(e.get("description")) == wanted]
    if unit is not None:
        wanted_unit = unit_label(unit)
        matches = [e for e in matches if _unit(e) == wanted_unit]
    if category is not None:
        matches = [e for e in matches if _category(e) == category]
    if brand is not None:
        wanted_brand = name_key(brand)
        matches = [e for e in matches if name_key(e.get("brand")) == wanted_brand]
    if shops is not None:
        wanted_shops = {name_key(s) for s in shops}
        matches = [e for e in matches if name_key(_shop_label(e)) in wanted_shops]
    return matches


def _most_used_spelling(spellings: list[str]) -> str:
    counts = Counter(spellings)
    return min(counts, key=lambda sp: (-counts[sp], sp))


def _trend_label(prices: list) -> str:
    """Whether prices went up or down: the oldest purchases against the newest.

    Up to 3 purchases are compared from each end, but never more than half the history,
    so the two groups never overlap. (Overlapping groups made short histories always
    "Stable": with 2 or 3 purchases both averages were the same numbers.)
    """
    window = min(3, len(prices) // 2)
    if window == 0:
        return "Stable"
    old_avg, recent_avg = mean(prices[:window]), mean(prices[-window:])
    return "Increasing" if recent_avg > old_avg else "Decreasing" if recent_avg < old_avg else "Stable"


def _iso(d) -> str:
    return d.isoformat() if hasattr(d, "isoformat") else d


def price_summary(rows: list[dict]) -> dict | None:
    """First/last/average/min/max price, change and trend over some purchases of one item.

    Works for any number of purchases (a single one has no change and no trend); returns
    None when there are none. Prices are per base unit, oldest purchase first.
    """
    if not rows:
        return None
    rows = sorted(rows, key=lambda e: e["date"])
    prices = [_price(e) for e in rows]
    first_price, last_price = prices[0], prices[-1]
    change = last_price - first_price
    change_pct = (change / first_price * 100) if first_price else 0.0
    return {
        "first_date": _iso(rows[0]["date"]),
        "last_date": _iso(rows[-1]["date"]),
        "first_price": quantize_money(first_price),
        "last_price": quantize_money(last_price),
        "change": quantize_money(change),
        "change_pct": round(change_pct, 1),
        "avg_price": quantize_money(mean(prices)),
        "min_price": quantize_money(min(prices)),
        "max_price": quantize_money(max(prices)),
        "volatility": round(pstdev(prices), 2) if len(prices) > 1 else 0.0,
        "trend": _trend_label(prices),
        "purchases": len(rows),
    }


def price_trends(expenses: list[dict]) -> list[dict]:
    """Price-change summary per (item, unit, category) triple, needs >= 2 purchases.

    Each result also lists the brands and shops the item was bought under, so the
    caller can offer them as choices for a finer comparison.
    """
    by_item: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for e in expenses:
        if str(e.get("description") or "").strip():
            by_item[(name_key(e["description"]), _unit(e), _category(e))].append(e)

    results = []
    for (_, unit, category), rows in by_item.items():
        if len(rows) < 2:
            continue
        item = _most_used_spelling([" ".join(str(r["description"]).split()) for r in rows])
        results.append({"item": item, "category": category, "unit": unit, **price_summary(rows)})

    return sorted(results, key=lambda r: r["change_pct"], reverse=True)


def comparison_options(matches: list[dict]) -> dict:
    """The brands and shops an item was bought under, with how many purchases each.

    Brand "" stands for purchases with no brand recorded. Most-bought first.
    """
    def tally(label_of) -> list[dict]:
        groups: dict[str, list[str]] = defaultdict(list)
        for e in matches:
            label = label_of(e)
            groups[name_key(label)].append(label)
        out = [{"name": _most_used_spelling(labels), "count": len(labels)} for labels in groups.values()]
        return sorted(out, key=lambda o: (-o["count"], o["name"].casefold()))

    return {
        "brands": tally(lambda e: clean_name(e.get("brand"))),
        "shops": tally(_shop_label),
    }


def _shop_rows(matches: list[dict]) -> list[dict]:
    by_shop: dict[str, list] = defaultdict(list)
    labels: dict[str, list[str]] = defaultdict(list)
    for e in matches:
        label = _shop_label(e)
        by_shop[name_key(label)].append(_price(e))
        labels[name_key(label)].append(label)
    rows = [
        {
            "shop": _most_used_spelling(labels[key]),
            "avg_price": round(mean(prices), 2),
            "min_price": round(min(prices), 2),
            "max_price": round(max(prices), 2),
            "times_bought": len(prices),
        }
        for key, prices in by_shop.items()
    ]
    return sorted(rows, key=lambda r: r["avg_price"])


def _history_rows(matches: list[dict]) -> list[dict]:
    return [
        {
            "date": _iso(e["date"]),
            "price": quantize_money(_price(e)),
            "shop": e.get("shop", ""),
            "brand": clean_name(e.get("brand")),
        }
        for e in sorted(matches, key=lambda e: e["date"])
    ]


def shop_comparison(
    expenses: list[dict],
    item: str,
    unit: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    shops: list[str] | None = None,
) -> list[dict]:
    """Compare average/min/max price of the same item (unit, category) across shops."""
    return _shop_rows(_matching(expenses, item, unit, category, brand, shops))


def price_history(
    expenses: list[dict],
    item: str,
    unit: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    shops: list[str] | None = None,
) -> list[dict]:
    """Timeline of (date, price, shop) points for a single item (unit, category), oldest first."""
    return _history_rows(_matching(expenses, item, unit, category, brand, shops))


def price_detail(
    expenses: list[dict],
    item: str,
    unit: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    shops: list[str] | None = None,
) -> dict:
    """Everything the detail view of one item needs, for the chosen brand and shops.

    `options` always describes the whole item (every brand and shop) so the choices
    stay put while the selection changes; `summary`, `shops` and `history` cover only
    the selection. By default (no brand, no shops) that is every purchase of the item.
    """
    everything = _matching(expenses, item, unit, category)
    selected = _matching(expenses, item, unit, category, brand, shops)
    return {
        "options": comparison_options(everything),
        "summary": price_summary(selected),
        "shops": _shop_rows(selected),
        "history": _history_rows(selected),
    }
