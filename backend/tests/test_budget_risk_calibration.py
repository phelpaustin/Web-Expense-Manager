"""Do the percentages mean what they say?

Simulates people who spend the way budgets are actually hit (rent on day 1, grocery shops on random days,
months that run busier or quieter, the odd lumpy purchase), asks for the chance of going over a grocery
budget part-way through each month using only what was known by then, and compares it with what happened.
Seeded, so it is the same every run. If a change quietly breaks what the numbers mean, this fails.
"""
import calendar
import datetime as dt
import math
import random
from decimal import Decimal as D

import pytest

from app.logic.budget_risk import ALERT_THRESHOLD, budget_risk


def simulate_user(rng, months=36, start=(2023, 1)):
    rent = rng.choice([0, 6000, 9000])
    shop_prob = rng.uniform(0.15, 0.5)
    shop_mu = rng.uniform(4.6, 5.8)
    rows = []
    for k in range(months):
        y, m = start[0] + (start[1] - 1 + k) // 12, (start[1] - 1 + k) % 12 + 1
        level = math.exp(rng.gauss(0, 0.25))                       # this month is busier or quieter than usual
        for d in range(1, calendar.monthrange(y, m)[1] + 1):
            if rent and d == 1:
                rows.append((dt.date(y, m, d), "Housing", rent))
            if rng.random() < shop_prob * min(level, 1.8):
                rows.append((dt.date(y, m, d), "Groceries", round(math.exp(rng.gauss(shop_mu, 0.45)), 2)))
            if rng.random() < 0.012:                              # a lumpy purchase
                rows.append((dt.date(y, m, d), "Groceries", round(math.exp(rng.gauss(7.0, 0.5)), 2)))
    return rows


def predictions(users=45, seed=11):
    """(chance, did it go over?) for every budget that was not yet blown, at the 7th, 14th and 21st."""
    rng = random.Random(seed)
    out = []
    for _ in range(users):
        rows = simulate_user(rng)
        by_month = {}
        for d, c, a in rows:
            if c == "Groceries":
                by_month[(d.year, d.month)] = by_month.get((d.year, d.month), 0) + a
        typical = sorted(by_month.values())[len(by_month) // 2]
        for k in range(14, 36):                                      # at least 12 earlier months to learn from
            y, m = 2023 + k // 12, k % 12 + 1
            budget = typical * rng.uniform(0.8, 1.5)
            final = sum(a for d, c, a in rows if c == "Groceries" and (d.year, d.month) == (y, m))
            for day in (7, 14, 21):
                today = dt.date(y, m, day)
                known = [{"date": d, "category": c, "amount": D(str(a))} for d, c, a in rows if d <= today]
                spent = sum(a for d, c, a in rows if c == "Groceries" and (d.year, d.month) == (y, m) and d <= today)
                status = {"category": "Groceries", "budget": D(str(round(budget, 2))), "spent": D(str(round(spent, 2))),
                          "remaining": D(str(round(budget - spent, 2))), "pct": 0.0, "status": "ok"}
                item = budget_risk(known, [status], None, today=today)["items"][0]
                if item["available"] and item["level"] != "over":
                    out.append((item["probability"] / 100, final > budget))
    return out


@pytest.fixture(scope="module")
def preds():
    return predictions()


def test_the_percentages_match_how_often_budgets_were_really_exceeded(preds):

    assert len(preds) > 2000
    for lo, hi in [(0.0, 0.15), (0.15, 0.4), (0.4, 0.7), (0.7, 1.01)]:
        chosen = [(p, o) for p, o in preds if lo <= p < hi]
        if len(chosen) < 150:
            continue
        predicted = sum(p for p, _ in chosen) / len(chosen)
        observed = sum(o for _, o in chosen) / len(chosen)
        assert abs(predicted - observed) <= 0.08, f"{lo:.0%}-{hi:.0%}: said {predicted:.1%}, happened {observed:.1%}"


def test_the_chances_are_clearly_better_than_always_guessing_the_overall_rate(preds):
    base = sum(o for _, o in preds) / len(preds)

    brier = sum((p - o) ** 2 for p, o in preds) / len(preds)
    guess = sum((base - o) ** 2 for _, o in preds) / len(preds)

    assert brier < guess - 0.04


def test_a_warning_at_the_alert_threshold_is_usually_right(preds):
    warned = [o for p, o in preds if p * 100 >= ALERT_THRESHOLD]

    assert len(warned) > 100
    assert sum(warned) / len(warned) >= 0.8
