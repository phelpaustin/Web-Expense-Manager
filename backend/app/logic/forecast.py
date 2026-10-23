"""Forecast this month's spending, with an honest range and a track record.

What is forecast
  The month after the last finished one, which is the month in progress. The forecast is of
  *baseline* spending: committed plus everyday, without one-offs (see spending_mix), so one big
  purchase last month doesn't inflate this month's number. One-offs are reported beside it.

How it is chosen
  Several simple methods are each tested the way they'd really be used: forecast a past month
  from only the months before it, compare with what happened, repeat over the last 6 months
  (12 when there is enough history to include every season). The method with the smallest
  error wins, but the simpler one is kept unless the fancier one is at least 5% more accurate,
  so a lucky fit to a few months can't win. The same errors size the range: its width is how
  far off the method has really been, widened for the small number of tests (Student's t).

What it needs
  3 finished months for a number, 5 to test it, 7 for a range (4 to learn from and 3 tests).
  Seasonal memory needs 27 months. Below that it says so rather than guess.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.core.money import as_decimal, quantize_money
from app.logic.category_change import UNCATEGORISED, _as_date
from app.logic.spending_mix import find_one_offs, shift_month

LEVEL = 80  # the range should contain the outcome about 80% of the time
MIN_MONTHS = 3
MIN_TRAIN = 4  # months a method learns from before its first test
MIN_TESTS_FOR_RANGE = 3
MAX_BACKTEST = 6
MAX_BACKTEST_SEASONAL = 12  # long enough that every calendar month is tested
SEASONAL_MIN_MONTHS = 27
IMPROVEMENT = 0.05  # a more complex method must beat a simpler one by this much
MAX_HISTORY = 36
CHART_MONTHS = 12
PARTIAL_START_DAY = 10  # tracking that began after this day of a month makes it a part month
DEFAULT_TOP = 6
ROLLUP = "Everything else"  # categories beyond the biggest few, added together
SEASONAL_RATIO_LIMITS = (0.5, 2.0)

# Two-sided 80% Student's t critical values by degrees of freedom (the number of tests);
# beyond 30 the normal value. Generated with scipy.stats.t.ppf(0.9, df).
_T80 = {
    1: 3.078, 2: 1.886, 3: 1.638, 4: 1.533, 5: 1.476, 6: 1.44, 7: 1.415, 8: 1.397, 9: 1.383, 10: 1.372,
    11: 1.363, 12: 1.356, 13: 1.35, 14: 1.345, 15: 1.341, 16: 1.337, 17: 1.333, 18: 1.33, 19: 1.328,
    20: 1.325, 21: 1.323, 22: 1.321, 23: 1.319, 24: 1.318, 25: 1.316, 26: 1.315, 27: 1.314, 28: 1.313,
    29: 1.311, 30: 1.31,
}
_Z80 = 1.2816


def t_multiplier(tests: int) -> float:
    return _T80.get(tests, _Z80)


# --- the methods: each takes the months so far (oldest first) and forecasts the next -----

def _naive(y: list[float]) -> float:
    return y[-1]


def _mean3(y: list[float]) -> float:
    recent = y[-3:]
    return sum(recent) / len(recent)


def _ses(y: list[float]) -> float:
    """Exponential smoothing: recent months count more; the weight is fitted to the history."""
    best = None
    for alpha in (0.2, 0.4, 0.6, 0.8):
        level, sse = y[0], 0.0
        for v in y[1:]:
            sse += (v - level) ** 2
            level = alpha * v + (1 - alpha) * level
        if best is None or sse < best[0]:
            best = (sse, level)
    return best[1]


def _holt_damped(y: list[float]) -> float:
    """Smoothed level plus a trend that fades out, so a rise doesn't run on forever."""
    best = None
    for alpha in (0.2, 0.5, 0.8):
        for beta in (0.1, 0.3):
            for phi in (0.8, 0.9, 0.98):
                level, trend, sse = y[0], y[1] - y[0], 0.0
                for v in y[1:]:
                    predicted = level + phi * trend
                    sse += (v - predicted) ** 2
                    new_level = alpha * v + (1 - alpha) * predicted
                    trend = beta * (new_level - level) + (1 - beta) * phi * trend
                    level = new_level
                if best is None or sse < best[0]:
                    best = (sse, level + phi * trend)
    return best[1]


def _seasonal(y: list[float]) -> float:
    """The same month a year ago, scaled by how recent months compare with a year ago."""
    year_ago = sum(y[-15:-12]) / 3
    ratio = sum(y[-3:]) / 3 / year_ago if year_ago > 0 else 1.0
    low, high = SEASONAL_RATIO_LIMITS
    return y[-12] * min(max(ratio, low), high)


# (name, plain-language label, function), simplest first
METHODS = [
    ("naive", "Same as last month", _naive),
    ("mean3", "Average of the last 3 months", _mean3),
    ("ses", "Smoothed average (recent months count more)", _ses),
    ("holt", "Smoothed trend (follows a steady rise or fall, fading out)", _holt_damped),
    ("seasonal", "Same month last year, adjusted for recent months", _seasonal),
]
_BY_NAME = {name: (label, fn) for name, label, fn in METHODS}


def _predict(name: str, y: list[float]) -> float:
    return max(0.0, _BY_NAME[name][1](y))


# --- testing and choosing ---------------------------------------------------------------

def _metrics(pairs: list[tuple[float, float]]) -> dict:
    errors = [actual - forecast for actual, forecast in pairs]
    n = len(errors)
    pct = [abs(e) / actual for e, (actual, _) in zip(errors, pairs) if actual > 0]
    return {
        "rmse": math.sqrt(sum(e * e for e in errors) / n),
        "mae": sum(abs(e) for e in errors) / n,
        "bias": sum(errors) / n,  # positive: spending tends to come in above the forecast
        "mape": sum(pct) / len(pct) * 100 if pct else None,
    }


def _choose(results: list[dict]) -> dict:
    """The most accurate method, preferring the simpler unless the other is clearly better."""
    best = results[0]
    for r in results[1:]:
        if r["rmse"] < best["rmse"] * (1 - IMPROVEMENT):
            best = r
    return best


def _fit(y: list[float]) -> dict | None:
    """Forecast the next value of a monthly series, with how it was tested."""
    n = len(y)
    if n < MIN_MONTHS:
        return None
    seasonal_ok = n >= SEASONAL_MIN_MONTHS
    tests = max(0, min(MAX_BACKTEST_SEASONAL if seasonal_ok else MAX_BACKTEST, n - MIN_TRAIN))

    results = []
    if tests >= 1:
        for name, label, _ in METHODS:
            if name == "seasonal" and not seasonal_ok:
                continue
            pairs = [(y[i], _predict(name, y[:i])) for i in range(n - tests, n)]
            results.append({"name": name, "label": label, **_metrics(pairs)})

    if tests >= MIN_TESTS_FOR_RANGE:
        chosen = _choose(results)
    else:  # too few tests to prefer one method over another: the steady, robust one
        chosen = next((r for r in results if r["name"] == "mean3"), {"name": "mean3", "label": _BY_NAME["mean3"][0]})
    point = _predict(chosen["name"], y)

    interval = None
    if tests >= MIN_TESTS_FOR_RANGE:
        half = t_multiplier(tests) * chosen["rmse"]
        interval = (max(0.0, point - half), point + half)

    naive = next((r for r in results if r["name"] == "naive"), None)
    accuracy = None
    if "rmse" in chosen:
        accuracy = {
            "months_tested": tests,
            "mape": chosen["mape"],
            "mae": chosen["mae"],
            "bias": chosen["bias"],
            "naive_mape": naive["mape"] if naive else None,
            "beats_naive": (chosen["rmse"] < naive["rmse"]) if naive and chosen["name"] != "naive" else None,
        }
    return {"model": chosen["name"], "label": chosen["label"], "point": point, "interval": interval,
            "accuracy": accuracy, "results": results, "tests": tests, "seasonal_considered": seasonal_ok}


# --- building the monthly series ----------------------------------------------------------

def _money(x: float | Decimal) -> Decimal:
    return quantize_money(Decimal(str(x)))


def _round(x: float | None, places: int = 1) -> float | None:
    return None if x is None else round(x, places)


def forecast(expenses: list[dict], today: date | None = None, top: int = DEFAULT_TOP) -> dict:
    """Forecast baseline spending for the month in progress; see the module docstring."""
    today = today or date.today()
    this_month = date(today.year, today.month, 1)
    last_done = shift_month(this_month, -1)

    usable = []
    for e in expenses:
        d = _as_date(e.get("date"))
        if d is not None and d <= today and as_decimal(e.get("amount")) > 0:
            usable.append((d, e))

    base = {
        "available": False, "reason": None, "month": this_month.strftime("%Y-%m"),
        "requirements": {"min_months": MIN_MONTHS, "months_to_test": MIN_TRAIN + 1, "months_for_range": MIN_TRAIN + MIN_TESTS_FOR_RANGE,
                         "months_for_seasons": SEASONAL_MIN_MONTHS},
        "level": LEVEL,
    }
    if not usable:
        return {**base, "reason": "no_spending", "months_available": 0}

    first = min(d for d, _ in usable)
    first_month = date(first.year, first.month, 1)
    skipped_first = first.day > PARTIAL_START_DAY  # recording began part-way through: not a full month
    if skipped_first:
        first_month = shift_month(first_month, 1)
    first_month = max(first_month, shift_month(last_done, -(MAX_HISTORY - 1)))
    if first_month > last_done:
        return {**base, "reason": "not_enough_history", "months_available": 0}

    keys, n = [], 0
    cursor = first_month
    while cursor <= last_done:
        keys.append(cursor.strftime("%Y-%m"))
        cursor = shift_month(cursor, 1)
    n = len(keys)
    index = {k: i for i, k in enumerate(keys)}

    flagged = find_one_offs(usable, today, since=first_month)
    baseline = [Decimal(0)] * n
    one_off = [Decimal(0)] * n
    by_category: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal(0)] * n)
    so_far = {"total": Decimal(0), "one_off": Decimal(0)}
    for i, (d, e) in enumerate(usable):
        amount = as_decimal(e.get("amount"))
        key = d.strftime("%Y-%m")
        if d >= this_month:
            so_far["total"] += amount
            if i in flagged and e.get("recurring_template_id") is None:
                so_far["one_off"] += amount
            continue
        if key not in index:
            continue
        m = index[key]
        if i in flagged:
            one_off[m] += amount
        else:
            baseline[m] += amount
            by_category[str(e.get("category") or "").strip() or UNCATEGORISED][m] += amount

    result = {**base, "months_available": n, "skipped_first_month": skipped_first}
    series = [float(v) for v in baseline]
    fit = _fit(series)
    if fit is None:
        return {**result, "reason": "not_enough_history"}

    point = _money(fit["point"])
    window = slice(max(0, n - CHART_MONTHS), n)
    recent_one_offs = one_off[window]
    average_one_off = sum(recent_one_offs, Decimal(0)) / len(recent_one_offs)
    so_far_baseline = so_far["total"] - so_far["one_off"]

    # Category forecasts: each its own series, then scaled so they add up to the total forecast.
    ranked = sorted(by_category, key=lambda c: (-sum(by_category[c][-6:], Decimal(0)), c))
    shown, rest = ranked[:top], ranked[top:]
    # (A real category that happens to share the roll-up's name keeps its own row: the roll-up is keyed apart.)
    parts = {c: by_category[c] for c in shown}
    rolled = bool(rest)
    if rest:
        parts[ROLLUP] = [sum((by_category[c][m] for c in rest), Decimal(0)) for m in range(n)]
    raw = {}
    for name, values in parts.items():
        f = _fit([float(v) for v in values])
        if f is not None and any(v > 0 for v in values[-6:]):
            raw[name] = f["point"]
    scale = (float(point) / sum(raw.values())) if sum(raw.values()) > 0 else 0.0
    categories = {name: _money(p * scale) for name, p in raw.items()}
    if categories:  # absorb rounding so the categories add up to the total exactly
        biggest = max(categories, key=lambda c: (categories[c], c))
        categories[biggest] += point - sum(categories.values(), Decimal(0))

    last_month_by = {name: quantize_money(values[-1]) for name, values in parts.items()}
    return {
        **result,
        "available": True,
        "reason": None,
        "forecast": {
            "point": point,
            "low": _money(fit["interval"][0]) if fit["interval"] else None,
            "high": _money(fit["interval"][1]) if fit["interval"] else None,
        },
        "model": {"name": fit["model"], "label": fit["label"], "seasonal_considered": fit["seasonal_considered"]},
        "accuracy": (
            {**{k: _round(v) if k in ("mape", "naive_mape") else (_money(v) if k in ("mae", "bias") else v)
                for k, v in fit["accuracy"].items()}}
            if fit["accuracy"] else None
        ),
        "candidates": [
            {"name": r["name"], "label": r["label"], "mape": _round(r["mape"]), "rmse": _money(r["rmse"]), "chosen": r["name"] == fit["model"]}
            for r in fit["results"]
        ],
        "so_far": {
            "day": today.day,
            "total": quantize_money(so_far["total"]),
            "baseline": quantize_money(so_far_baseline),
            "one_off": quantize_money(so_far["one_off"]),
        },
        "one_offs": {
            "average_per_month": quantize_money(average_one_off),
            "months_with_one_offs": sum(1 for v in recent_one_offs if v > 0),
            "window_months": len(recent_one_offs),
            "with_one_offs": quantize_money(point + average_one_off),
        },
        "history": [
            {"month": keys[m], "baseline": quantize_money(baseline[m]), "one_off": quantize_money(one_off[m]),
             "total": quantize_money(baseline[m] + one_off[m])}
            for m in range(window.start, n)
        ],
        "categories": [
            {
                "category": name,
                "forecast": amount,
                "last_month": last_month_by.get(name, quantize_money(0)),
                "change": amount - last_month_by.get(name, quantize_money(0)),
                "share_pct": round(float(amount / point * 100), 1) if point else None,
                "rollup": rolled and name == ROLLUP,
            }
            for name, amount in sorted(categories.items(), key=lambda kv: (rolled and kv[0] == ROLLUP, -kv[1], kv[0]))
        ],
    }
