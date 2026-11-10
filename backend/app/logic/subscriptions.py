"""Find subscriptions the user never set up: purchases that repeat at a steady rhythm.

"Spotify 119 kr every month for 14 months, Netflix went up from 109 to 129 kr, the gym last charged
five months ago." Purchases are grouped by shop (or by description when there is no shop) and
currency. A group is a subscription when its charges come at a steady gap (weekly, bi-weekly,
monthly, quarterly or yearly) for at least a few times, with amounts that stay close to each other.
Pure functions on plain dicts: no DB, no FastAPI.

Amounts are compared in their own currency, so exchange rates never look like price changes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from statistics import median

from app.core.money import as_decimal, quantize_money
from app.logic.names import clean_name, name_key
from app.logic.recurring import following_date
from app.logic.recurring_costs import monthly_cost, price_change, yearly_cost

# (frequency, shortest and longest gap in days that still counts, charges needed before we say so).
CADENCES = [
    ("Weekly", 6, 8, 5),
    ("Bi-weekly", 13, 15, 4),
    ("Monthly", 27, 34, 3),
    ("Quarterly", 85, 97, 3),
    ("Yearly", 350, 380, 2),
]
# Days after the expected date before a subscription counts as stopped.
GRACE_DAYS = {"Weekly": 5, "Bi-weekly": 5, "Monthly": 10, "Quarterly": 25, "Yearly": 30}
RHYTHM_SHARE = 0.75           # this share of the gaps must fit the rhythm
FIXED_TOLERANCE = Decimal("0.10")   # amounts within 10% of the usual: a fixed price
VARYING_TOLERANCE = Decimal("0.30")  # within 30%: a bill that varies a little (phone, gym with extras)
STEP = Decimal("0.02")        # a charge that differs from the one before by more than 2% is a price step
MAX_STEPS = 2                 # up to this many steps: a fixed price with rises or cuts
STOPPED_KEEP_DAYS = 400       # a subscription that stopped longer ago is not worth listing


def _cadence(gaps: list[int]) -> tuple[str, int, int, int] | None:
    typical = median(gaps)
    for frequency, low, high, needed in CADENCES:
        if low <= typical <= high:
            fit = sum(1 for g in gaps if low <= g <= high) / len(gaps)
            return (frequency, low, high, needed) if fit >= RHYTHM_SHARE else None
    return None


def _share_within(amounts: list[Decimal], usual: Decimal, tolerance: Decimal) -> float:
    return sum(1 for a in amounts if abs(a - usual) <= usual * tolerance) / len(amounts)


def _group_key(p: dict) -> str:
    return name_key(p.get("shop") or "") or name_key(p.get("description") or "")


def find_subscriptions(
    purchases: list[dict],
    tracked_keys: set[str] | frozenset[str] = frozenset(),
    ignored_keys: set[str] | frozenset[str] = frozenset(),
    today: date | None = None,
) -> dict:
    """Subscriptions in ``purchases`` (dicts with date, amount, currency, shop, description, category,
    and ``tracked`` when a recurring template already posted it).

    ``tracked_keys`` are name keys of recurring templates; a subscription matching one is counted but
    not listed. ``ignored_keys`` are names the user said are not subscriptions.
    """
    today = today or date.today()
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in purchases:
        amount = as_decimal(p["amount"])
        key = _group_key(p)
        if amount <= 0 or not key or key in ignored_keys:
            continue
        groups[(key, p.get("currency") or "")].append({**p, "amount": amount})

    active, stopped, tracked_count = [], [], 0
    for (key, currency), rows in groups.items():
        one_per_day: dict[date, dict] = {}
        for p in sorted(rows, key=lambda r: (r["date"], r.get("id") or 0)):
            one_per_day.setdefault(p["date"], p)
        charges = list(one_per_day.values())
        if len(charges) < 2:
            continue
        gaps = [(b["date"] - a["date"]).days for a, b in zip(charges, charges[1:])]
        cadence = _cadence(gaps)
        if cadence is None or len(charges) < cadence[3]:
            continue
        frequency = cadence[0]

        amounts = [c["amount"] for c in charges]
        # A price that stays put, or steps up or down once or twice, is a fixed price with price changes.
        # A price that moves all the time must stay close to its usual level, and is "varying".
        steps = sum(1 for a, b in zip(amounts, amounts[1:]) if abs(b - a) > a * STEP)
        usual = as_decimal(median(amounts))
        if steps <= MAX_STEPS:
            varies = False
        else:
            if _share_within(amounts, usual, VARYING_TOLERANCE) < RHYTHM_SHARE:
                continue
            varies = _share_within(amounts, usual, FIXED_TOLERANCE) < RHYTHM_SHARE

        last = charges[-1]
        if any(c.get("tracked") for c in charges) or key in tracked_keys:
            tracked_count += 1
            continue

        expected = following_date(last["date"], frequency)
        is_stopped = (today - expected).days > GRACE_DAYS[frequency]
        if is_stopped and (today - last["date"]).days > STOPPED_KEEP_DAYS:
            continue

        names = Counter(clean_name(c.get("shop") or c.get("description")) for c in charges)
        categories = Counter(c.get("category") or "" for c in charges)
        item = {
            "key": key,
            "name": sorted(names.items(), key=lambda kv: (-kv[1], kv[0]))[0][0],
            "category": sorted(categories.items(), key=lambda kv: (-kv[1], kv[0]))[0][0],
            "currency": currency,
            "amount": quantize_money(last["amount"]),
            "frequency": frequency,
            "monthly_native": monthly_cost(last["amount"], frequency),
            "yearly_native": yearly_cost(last["amount"], frequency),
            "first_date": charges[0]["date"],
            "last_date": last["date"],
            "next_due": expected,
            "charges": len(charges),
            "varies": varies,
            "price_change": price_change(charges) if steps <= MAX_STEPS else None,
        }
        (stopped if is_stopped else active).append(item)

    active.sort(key=lambda i: (-i["monthly_native"], i["name"].lower()))
    stopped.sort(key=lambda i: (i["last_date"], i["name"].lower()), reverse=True)
    return {"items": active, "stopped": stopped, "tracked_count": tracked_count}


__all__ = ["find_subscriptions", "CADENCES"]
