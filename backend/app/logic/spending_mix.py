"""How much of your spending is committed, everyday, or a one-off?

  committed  posted by a recurring template (rent, subscriptions): already agreed.
  one-off    a purchase far bigger than is usual for you (annual insurance, a new laptop).
  everyday   everything else.

Every expense is exactly one of these, so each month's three parts add up to its total.
Committed wins over one-off: a large recurring payment is committed, not unusual.

The one-off rule (kept simple enough to explain in a sentence)
  An expense is a one-off when it is more than 3 times, and also well above the spread of,
  what you usually spend on that category. "Usual" is the median of your non-committed
  purchases in the category over the last year and the spread is the median absolute
  deviation, so a few big purchases don't hide themselves by dragging the average up.
  A category with fewer than MIN_SAMPLES purchases can't say what usual is, so it is judged
  against your purchases overall instead; with too few of those the expense isn't judged.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from statistics import median

from app.core.money import as_decimal, quantize_money
from app.logic.category_change import _as_date

DEFAULT_MONTHS = 12
MAX_MONTHS = 12
MIN_SAMPLES = 8  # purchases needed before "usual" means anything
MIN_MULTIPLE = 3  # a one-off is at least this many times the usual purchase...
SIGMAS = 3  # ...and this many robust standard deviations above it
REFERENCE_DAYS = 365
MAX_ONE_OFFS = 8
MAX_COMMITTED = 5
_MAD_TO_SIGMA = Decimal("1.4826")  # scales the median absolute deviation to a standard deviation
_ZERO = quantize_money(0)


def shift_month(first_of_month: date, months: int) -> date:
    """The first of the month `months` away from the one given (negative goes back)."""
    index = first_of_month.year * 12 + first_of_month.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _usual_and_threshold(amounts: list[Decimal]) -> tuple[Decimal, Decimal]:
    """(usual purchase, the amount above which one is a one-off) for some purchases."""
    usual = Decimal(median(amounts))
    spread = Decimal(median([abs(a - usual) for a in amounts])) * _MAD_TO_SIGMA
    if spread == 0:  # all alike: judge by the multiple alone, with a quarter of usual as the spread
        spread = usual / 4
    return usual, max(usual + SIGMAS * spread, MIN_MULTIPLE * usual)


def find_one_offs(usable: list[tuple[date, dict]], today: date, since: date) -> dict[int, dict]:
    """Which of the expenses are one-offs, as {index into `usable`: why}.

    `usable` is (date, expense) pairs with a positive amount and no future date. Only
    expenses on or after `since` can be flagged; what is usual is measured over the last
    year (or back to `since`, if that is further).
    """
    reference_start = min(since, date.fromordinal(today.toordinal() - REFERENCE_DAYS))
    pool = [(i, e, as_decimal(e.get("amount"))) for i, (d, e) in enumerate(usable)
            if d >= reference_start and e.get("recurring_template_id") is None]
    by_category: dict[str, list[Decimal]] = defaultdict(list)
    for _, e, amount in pool:
        by_category[str(e.get("category") or "").strip()].append(amount)
    overall = [amount for _, _, amount in pool]

    cache: dict[object, tuple[Decimal, Decimal]] = {}

    def basis_for(category: str):
        if len(by_category[category]) >= MIN_SAMPLES:
            return category, "category", by_category[category]
        if len(overall) >= MIN_SAMPLES:
            return "", "overall", overall
        return None

    flagged: dict[int, dict] = {}
    for i, e, amount in pool:
        if usable[i][0] < since:
            continue
        chosen = basis_for(str(e.get("category") or "").strip())
        if chosen is None:
            continue
        key, basis, amounts = chosen
        cache_key = (basis, key)
        if cache_key not in cache:
            cache[cache_key] = _usual_and_threshold(amounts)
        usual, threshold = cache[cache_key]
        if amount > threshold:
            flagged[i] = {"usual": usual, "ratio": float(amount / usual), "basis": basis}
    return flagged


def spending_mix(expenses: list[dict], today: date | None = None, months: int = DEFAULT_MONTHS, top: int = MAX_ONE_OFFS) -> dict:
    """Month by month split of spending into committed, everyday and one-off, plus the details."""
    today = today or date.today()
    months = max(1, min(months, MAX_MONTHS))
    this_month = date(today.year, today.month, 1)
    first_month = shift_month(this_month, -(months - 1))

    usable = []
    for e in expenses:
        d = _as_date(e.get("date"))
        if d is not None and d <= today and as_decimal(e.get("amount")) > 0:
            usable.append((d, e))
    flagged = find_one_offs(usable, today, since=first_month)

    keys = [_key(shift_month(first_month, n)) for n in range(months)]
    raw = {k: {"committed": Decimal(0), "everyday": Decimal(0), "one_off": Decimal(0)} for k in keys}
    one_offs, committed = [], defaultdict(lambda: {"total": Decimal(0), "count": 0, "names": Counter(), "last": None})
    in_window = False
    for i, (d, e) in enumerate(usable):
        if d < first_month:
            continue
        in_window = True
        amount = as_decimal(e.get("amount"))
        if e.get("recurring_template_id") is not None:
            raw[_key(d)]["committed"] += amount
            c = committed[e["recurring_template_id"]]
            c["total"] += amount
            c["count"] += 1
            c["names"][str(e.get("description") or "").strip() or str(e.get("category") or "")] += 1
            c["last"] = max(c["last"], d) if c["last"] else d
        elif i in flagged:
            raw[_key(d)]["one_off"] += amount
            one_offs.append((amount, d, e, flagged[i]))
        else:
            raw[_key(d)]["everyday"] += amount

    month_rows = []
    for k in keys:
        parts = {name: quantize_money(v) for name, v in raw[k].items()}
        month_rows.append({"month": k, **parts, "total": sum(parts.values(), _ZERO), "partial": k == _key(this_month)})

    totals = {name: sum((m[name] for m in month_rows), _ZERO) for name in ("committed", "everyday", "one_off")}
    totals["total"] = sum(totals.values(), _ZERO)

    def pct(part):
        return round(float(part / totals["total"] * 100), 1) if totals["total"] else None

    # A typical month: the finished months since you started recording (the month in
    # progress would drag the average down). Needs at least two to mean anything.
    started = next((i for i, m in enumerate(month_rows) if m["total"] > 0), None)
    finished = [m for m in month_rows[started:] if not m["partial"]] if started is not None else []
    typical = None
    if len(finished) >= 2:
        avg = {name: quantize_money(sum((m[name] for m in finished), _ZERO) / len(finished)) for name in ("committed", "everyday", "one_off")}
        typical = {"months": len(finished), **avg, "baseline": avg["committed"] + avg["everyday"], "total": sum(avg.values(), _ZERO)}

    one_offs.sort(key=lambda t: (-t[0], t[1].isoformat(), str(t[2].get("description") or "")))
    return {
        "window": {"from": first_month.isoformat(), "to": today.isoformat(), "months": months},
        "available": in_window,
        "months": month_rows,
        "typical": typical,
        "totals": {**totals, "committed_pct": pct(totals["committed"]), "one_off_pct": pct(totals["one_off"])},
        "one_off_count": len(one_offs),
        "one_offs": [
            {
                "id": e.get("id"),
                "date": d.isoformat(),
                "description": str(e.get("description") or "").strip(),
                "category": str(e.get("category") or "").strip(),
                "shop": str(e.get("shop") or "").strip(),
                "amount": quantize_money(amount),
                "usual": quantize_money(why["usual"]),
                "ratio": round(why["ratio"], 1),
                "basis": why["basis"],
            }
            for amount, d, e, why in one_offs[:top]
        ],
        "committed_top": [
            {
                "template_id": tid,
                "description": min(c["names"], key=lambda n: (-c["names"][n], n)),
                "total": quantize_money(c["total"]),
                "count": c["count"],
                "last_date": c["last"].isoformat(),
            }
            for tid, c in sorted(committed.items(), key=lambda kv: (-kv[1]["total"], kv[0]))[:MAX_COMMITTED]
        ],
        "rule": {"min_samples": MIN_SAMPLES, "multiple": MIN_MULTIPLE, "sigmas": SIGMAS},
    }
