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
from datetime import date, timedelta
from decimal import Decimal
from statistics import mean as _mean_any, pstdev as _pstdev_any

from app.core.money import quantize_money
from app.logic.names import clean_name, name_key
from app.logic.units import to_base_price, unit_label


def mean(values):
    """Mean of prices. For Decimals this is the same exact result as statistics.mean (the sum
    of 4-decimal prices is exact, so one division gives the same digits) without its slow
    per-value Fraction arithmetic, which dominated the page's time."""
    values = list(values)
    if values and all(isinstance(v, Decimal) for v in values):
        return sum(values, Decimal(0)) / len(values)
    return _mean_any(values)


def pstdev(values):
    values = list(values)
    if len(values) > 1 and all(isinstance(v, Decimal) for v in values):
        mu = sum(values, Decimal(0)) / len(values)
        return (sum(((v - mu) ** 2 for v in values), Decimal(0)) / len(values)).sqrt()
    return _pstdev_any(values)


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


def _is_item_purchase(e: dict) -> bool:
    """False for a bill recorded as a single total: its description is just the shop's name
    and its amount is a whole trip, so it says nothing about any item's price."""
    return not e.get("bill_total_only")


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
    matches = [e for e in expenses if _is_item_purchase(e) and name_key(e.get("description")) == wanted]
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
        if _is_item_purchase(e) and str(e.get("description") or "").strip():
            by_item[(name_key(e["description"]), _unit(e), _category(e))].append(e)

    results = []
    for (_, unit, category), rows in by_item.items():
        if len(rows) < 2:
            continue
        item = _most_used_spelling([" ".join(str(r["description"]).split()) for r in rows])
        results.append({"item": item, "category": category, "unit": unit, **price_summary(rows)})

    return sorted(results, key=lambda r: r["change_pct"], reverse=True)


DEFAULT_CHEAPEST_MONTHS = 12
DEFAULT_MIN_SAVING_PCT = 5.0


def _months_ago_start(today: date, months: int) -> date:
    index = today.year * 12 + today.month - 1 - months
    return date(index // 12, index % 12 + 1, 1)


def _as_day(value) -> date | None:
    if isinstance(value, date):
        return value.date() if hasattr(value, "date") and callable(value.date) else value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def cheapest_shops(
    expenses: list[dict],
    today: date | None = None,
    months: int = DEFAULT_CHEAPEST_MONTHS,
    min_saving_pct: float = DEFAULT_MIN_SAVING_PCT,
    top: int = 10,
) -> dict:
    """Items bought at more than one shop, where a shop you use less is cheaper than your usual one.

    The same product is compared: item, unit, category and brand all have to match, so a cheaper
    shop is not just a cheaper brand. Prices are per base unit, averaged per shop over the last
    `months` months (0 = all time), so an old price does not decide today's answer. Purchases with
    no shop are left out, since "Unknown" cannot be recommended. "Your usual shop" is where you
    bought the item most often (a tie goes to the one you used last).

    An item is listed only when the cheapest shop is not your usual one and saves at least
    `min_saving_pct` percent per unit. Items where your usual shop is already the cheapest are
    only counted, so you can be told so.
    """
    today = today or date.today()
    cutoff = _months_ago_start(today, months) if months > 0 else None

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for e in expenses:
        if not _is_item_purchase(e) or not str(e.get("description") or "").strip() or not clean_name(e.get("shop")):
            continue
        day = _as_day(e.get("date"))
        if day is None or (cutoff is not None and day < cutoff):
            continue
        groups[(name_key(e["description"]), _unit(e), _category(e), name_key(e.get("brand")))].append({**e, "_day": day})

    listed, compared, already = [], 0, 0
    for (_, unit, category, _brand), rows in groups.items():
        by_shop: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by_shop[name_key(_shop_label(r))].append(r)
        if len(by_shop) < 2:
            continue
        compared += 1

        stats = []
        for shop_rows in by_shop.values():
            prices = [_price(r) for r in shop_rows]
            stats.append({
                "shop": _most_used_spelling([_shop_label(r) for r in shop_rows]),
                "avg_price": quantize_money(mean(prices)),
                "times_bought": len(prices),
                "last_date": _iso(max(r["_day"] for r in shop_rows)),
            })
        cheapest = min(stats, key=lambda x: (x["avg_price"], -x["times_bought"], x["shop"].casefold()))
        usual = max(stats, key=lambda x: (x["times_bought"], x["last_date"]))
        if cheapest is usual or usual["avg_price"] <= 0:
            already += 1
            continue
        saving = usual["avg_price"] - cheapest["avg_price"]
        pct = round(float(saving / usual["avg_price"] * 100), 1)
        if saving <= 0 or pct < min_saving_pct:
            if saving <= 0:
                already += 1  # the usual shop is as cheap as any
            continue
        listed.append({
            "item": _most_used_spelling([" ".join(str(r["description"]).split()) for r in rows]),
            "brand": _most_used_spelling([clean_name(r.get("brand")) for r in rows]),
            "unit": unit,
            "category": category,
            "shops_compared": len(stats),
            "cheapest": cheapest,
            "usual": usual,
            "saving_per_unit": quantize_money(saving),
            "saving_pct": pct,
        })

    listed.sort(key=lambda i: (-i["saving_pct"], -i["usual"]["times_bought"], i["item"].casefold()))
    return {
        "months": months,
        "compared": compared,
        "already_cheapest": already,
        "items": listed[:top],
        "total_found": len(listed),
    }


DEFAULT_RISE_PCT = 10.0
DEFAULT_RECENT_DAYS = 30
DEFAULT_BASELINE_MONTHS = 12
MIN_EARLIER_PURCHASES = 2


def rows_for_price_rises(expenses: list[dict], today: date | None = None, baseline_months: int = DEFAULT_BASELINE_MONTHS) -> list[dict]:
    """The expenses that can matter to `price_rises`: item purchases within the baseline window.

    Used before the (costly) renaming by the user's merges, so the bell does not rename years of
    history it will never look at. Everything is kept when `baseline_months` is 0.
    """
    today = today or date.today()
    start = _months_ago_start(today, baseline_months) if baseline_months > 0 else None
    out = []
    for e in expenses:
        if e.get("bill_total_only"):
            continue
        day = _as_day(e.get("date"))
        if day is None or day > today or (start is not None and day < start):
            continue
        out.append(e)
    return out


def price_rises(
    expenses: list[dict],
    today: date | None = None,
    recent_days: int = DEFAULT_RECENT_DAYS,
    min_rise_pct: float = DEFAULT_RISE_PCT,
    baseline_months: int = DEFAULT_BASELINE_MONTHS,
    min_earlier: int = MIN_EARLIER_PURCHASES,
    top: int = 10,
) -> dict:
    """Items whose latest price, at the shop you bought it at, is well above what you usually paid.

    The same product at the same shop is followed (item, unit, category, brand and shop), so
    switching shop or brand is never mistaken for a price rise. The newest purchase has to be from the
    last `recent_days` days, and is set against the average of the earlier purchases within
    `baseline_months` months (at least `min_earlier` of them, so one odd price cannot be "usual").
    A rise is reported from `min_rise_pct` percent. Prices are per base unit.
    """
    today = today or date.today()
    window_start = today - timedelta(days=recent_days)
    baseline_start = _months_ago_start(today, baseline_months) if baseline_months > 0 else None

    # Purchases from before the baseline can be neither the newest nor an "earlier" one, so they are
    # skipped at once: with years of history that is most rows.
    groups: dict[tuple, list[tuple]] = defaultdict(list)
    for e in expenses:
        day = _as_day(e.get("date"))
        if day is None or day > today or (baseline_start is not None and day < baseline_start):
            continue
        if not _is_item_purchase(e) or not str(e.get("description") or "").strip():
            continue
        key = (name_key(e["description"]), _unit(e), _category(e), name_key(e.get("brand")), name_key(_shop_label(e)))
        groups[key].append((day, e.get("id") or 0, e))

    found, checked = [], 0
    for entries in groups.values():
        entries.sort(key=lambda t: (t[0], t[1]))
        if entries[-1][0] < window_start:
            continue
        rows = [{**t[2], "_day": t[0]} for t in entries]
        latest = rows[-1]
        earlier = rows[:-1]
        if len(earlier) < min_earlier:
            continue
        checked += 1
        usual = mean([_price(r) for r in earlier])
        now = _price(latest)
        if usual <= 0 or now <= usual:
            continue
        pct = round(float((now - usual) / usual * 100), 1)
        if pct < min_rise_pct:
            continue
        found.append({
            "item": _most_used_spelling([" ".join(str(r["description"]).split()) for r in rows]),
            "brand": _most_used_spelling([clean_name(r.get("brand")) for r in rows]),
            "shop": _most_used_spelling([_shop_label(r) for r in rows]),
            "unit": _unit(latest),
            "category": _category(latest),
            "latest_price": quantize_money(now),
            "latest_date": _iso(latest["_day"]),
            "usual_price": quantize_money(usual),
            "rise_per_unit": quantize_money(now - usual),
            "rise_pct": pct,
            "earlier_purchases": len(earlier),
        })

    found.sort(key=lambda i: (-i["rise_pct"], i["item"].casefold(), i["shop"].casefold()))
    return {
        "recent_days": recent_days,
        "min_rise_pct": min_rise_pct,
        "checked": checked,
        "items": found[:top],
        "total_found": len(found),
    }


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
