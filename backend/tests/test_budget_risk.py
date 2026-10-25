"""The chance of exceeding each budget, from what the same stretch of earlier periods looked like."""
import datetime as dt
from decimal import Decimal as D

import pytest

from app.logic import budget_risk as br

TODAY = dt.date(2026, 10, 21)  # a Wednesday; 10 days left in the month


def row(date, category, amount):
    return {"date": dt.date.fromisoformat(date), "category": category, "amount": D(str(amount))}


def late_spending(category, amounts, last_month=(2026, 9), day=28):
    """One purchase on the 28th of each earlier month, newest month last: the remainder after the 21st
    is exactly that amount. `amounts` runs oldest to newest, ending at `last_month`."""
    year, month = last_month
    index = year * 12 + month - 1 - (len(amounts) - 1)
    return [row(f"{(index + i) // 12}-{(index + i) % 12 + 1:02d}-{day:02d}", category, a) for i, a in enumerate(amounts)]


def status(category, budget, spent):
    return {"category": category, "budget": D(budget), "spent": D(spent), "remaining": D(budget) - D(spent),
            "pct": round(float(spent) / float(budget) * 100, 1) if budget else 0.0, "status": "ok"}


def period(effective=11000, spent=10200, kind="Monthly", days_remaining=10, projected=15000):
    return {"period": kind, "label": "October 2026", "budget": D(effective), "rollover": D(0), "effective": D(effective),
            "spent": D(spent), "remaining": D(effective) - D(spent), "pct": round(spent / effective * 100, 1), "projected": D(projected),
            "days_total": 31, "days_elapsed": 31 - days_remaining, "days_remaining": days_remaining, "status": "ok"}


def risk(rows, categories=(), total=None, today=TODAY):
    return br.budget_risk(rows, list(categories), total, today=today)


def item(result, name):
    return next(i for i in result["items"] if i["category"] == name)


# --- the same stretch of earlier periods ------------------------------------------------------

def test_remainders_are_the_spending_in_the_days_after_the_same_point_of_each_earlier_month():
    days = {dt.date(2026, 8, 21): D(999),          # the 21st itself is not "after"
            dt.date(2026, 8, 28): D(10),
            dt.date(2026, 9, 1): D(100),           # before the 21st
            dt.date(2026, 9, 22): D(50), dt.date(2026, 9, 30): D(25),
            dt.date(2026, 10, 25): D(5000)}         # the month in progress is not a sample

    assert br.remainders(days, "month", TODAY, drop_partial_start=False) == [D(10), D(75)]


def test_quiet_months_between_are_real_zeros_and_only_the_last_twelve_periods_count():
    days = {dt.date(2024, 1, 28): D(7), dt.date(2026, 9, 28): D(9)}                 # nothing in the 20 months between

    got = br.remainders(days, "month", TODAY, drop_partial_start=False)

    assert len(got) == br.MAX_PERIODS and got[-1] == D(9) and got[:-1] == [D(0)] * 11


def test_a_short_earlier_month_simply_has_nothing_left_after_the_cut():
    today = dt.date(2026, 3, 30)
    days = {dt.date(2026, 2, 27): D(40), dt.date(2026, 2, 28): D(60)}               # February ends on the 28th

    assert br.remainders(days, "month", today, drop_partial_start=False) == [D(0)]


def test_weekly_periods_line_up_by_weekday():
    wednesday = dt.date(2026, 10, 21)
    days = {dt.date(2026, 10, 12): D(1),   # Monday
            dt.date(2026, 10, 14): D(2),   # Wednesday: not after
            dt.date(2026, 10, 15): D(30),  # Thursday
            dt.date(2026, 10, 18): D(400)}  # Sunday of the same week

    assert br.remainders(days, "week", wednesday, drop_partial_start=False) == [D(430)]


def test_a_first_period_that_began_after_the_window_opened_is_left_out_when_asked():
    started_late = {dt.date(2026, 6, 25): D(100), dt.date(2026, 7, 28): D(7), dt.date(2026, 8, 28): D(8), dt.date(2026, 9, 28): D(9)}
    # Today is the 10th: June's window (after the 10th) opened before recording began on the 25th.
    today = dt.date(2026, 10, 10)

    assert br.remainders(started_late, "month", today, drop_partial_start=True) == [D(7), D(8), D(9)]
    assert br.remainders(started_late, "month", today, drop_partial_start=False) == [D(100), D(7), D(8), D(9)]


def test_a_first_period_whose_window_was_fully_recorded_is_kept():
    days = {dt.date(2026, 6, 11): D(100), dt.date(2026, 7, 28): D(7), dt.date(2026, 8, 28): D(8), dt.date(2026, 9, 28): D(9)}

    assert br.remainders(days, "month", dt.date(2026, 10, 10), drop_partial_start=True)[0] == D(100)   # began on the 11th: window opens then


def test_nothing_recorded_gives_no_samples():
    assert br.remainders({}, "month", TODAY, drop_partial_start=False) == []


# --- the chance --------------------------------------------------------------------------------

def test_the_chance_is_the_share_of_earlier_periods_that_went_past_what_is_left_nudged_off_the_ends():
    rows = late_spending("Groceries", [10, 100, 200, 300, 400])       # five earlier months

    r = risk(rows, [status("Groceries", 1000, 850)])                    # 150 left

    g = item(r, "Groceries")
    assert (g["samples"], g["exceeded"]) == (5, 3)                      # 200, 300 and 400 are more than 150
    assert g["probability"] == pytest.approx(3.5 / 6 * 100, abs=0.05) and g["level"] == "likely"
    assert g["typical_remaining"] == D("200.00")


def test_having_exactly_as_much_left_as_a_past_month_spent_is_not_exceeding():
    rows = late_spending("Groceries", [100, 100, 100, 100])

    g = item(risk(rows, [status("Groceries", 1000, 900)]), "Groceries")        # exactly 100 left

    assert g["exceeded"] == 0 and g["probability"] == pytest.approx(0.5 / 5 * 100)


def test_it_is_never_certain_or_impossible_from_history_alone():
    over = item(risk(late_spending("A", [500] * 8), [status("A", 1000, 900)]), "A")        # 100 left, every month spent 500
    safe = item(risk(late_spending("A", [5] * 8), [status("A", 1000, 900)]), "A")           # 100 left, every month spent 5

    assert over["exceeded"] == 8 and over["probability"] == pytest.approx(8.5 / 9 * 100, abs=0.05)
    assert over["probability"] < 100
    assert safe["exceeded"] == 0 and safe["probability"] == pytest.approx(0.5 / 9 * 100, abs=0.05)
    assert safe["probability"] > 0


def test_already_over_budget_is_certain_and_needs_no_history():
    g = item(risk([], [status("Groceries", 1000, 1200)]), "Groceries")

    assert g["available"] and g["probability"] == 100.0 and g["level"] == "over"


def test_when_the_period_ends_today_and_the_budget_held_there_is_nothing_left_to_go_wrong():
    today = dt.date(2026, 10, 31)

    g = item(risk([], [status("Groceries", 1000, 900)], today=today), "Groceries")

    assert g["available"] and g["probability"] == 0.0 and g["days_remaining"] == 0


def test_it_needs_four_earlier_periods_and_says_so():
    three = item(risk(late_spending("Groceries", [100, 200, 300]), [status("Groceries", 1000, 900)]), "Groceries")
    four = item(risk(late_spending("Groceries", [100, 200, 300, 400]), [status("Groceries", 1000, 900)]), "Groceries")

    assert (three["available"], three["reason"], three["samples"], three["probability"]) == (False, "not_enough_history", 3, None)
    assert four["available"] and four["samples"] == 4


def test_only_the_latest_twelve_periods_are_used():
    r = risk(late_spending("A", [900] * 10 + [0] * 12), [status("A", 1000, 800)])           # 22 months; recent 12 are zeros

    a = item(r, "A")
    assert a["samples"] == 12 and a["exceeded"] == 0


@pytest.mark.parametrize("p, name", [(100, "very_likely"), (75, "very_likely"), (74.9, "likely"), (50, "likely"), (49.9, "possible"),
                                     (25, "possible"), (24.9, "unlikely"), (0, "unlikely")])
def test_levels(p, name):
    assert br.level_for(p) == name


# --- what straight-line projection gets wrong ---------------------------------------------------

def test_rent_paid_on_day_one_does_not_make_the_month_look_doomed():
    rows = []
    for m in range(1, 10):
        rows.append(row(f"2026-{m:02d}-01", "Housing", 9000))
        rows += [row(f"2026-{m:02d}-{d:02d}", "Groceries", a) for d, a in ((3, 280), (9, 300), (14, 310), (19, 290), (24, 300), (28, 310))]
    rows += [row("2026-10-01", "Housing", 9000)] + [row(f"2026-10-{d:02d}", "Groceries", a) for d, a in ((3, 300), (9, 310), (14, 290), (19, 300))]
    total = period(effective=11000, spent=10200, projected=15000)          # straight line: 10,200 / 21 * 31 = 15,057

    r = risk(rows, [status("Groceries", 1800, 1200), status("Housing", 9500, 9000)], total)

    assert total["projected"] > total["effective"]                           # the old rule would warn, every month
    assert item(r, "Total")["probability"] < 10                              # 800 left; the rest of a month costs ~600
    assert item(r, "Groceries")["level"] in ("likely", "very_likely")        # 600 left against a typical 614


# --- which budgets, and from which numbers ------------------------------------------------------

def test_the_total_uses_the_period_status_numbers_including_rollover():
    ps = period(effective=12500, spent=11000)
    ps["rollover"] = D(1500)

    t = item(risk(late_spending("X", [100] * 5), [], ps), "Total")

    assert (t["limit"], t["spent"], t["remaining"], t["is_total"]) == (D("12500.00"), D("11000.00"), D("1500.00"), True)
    assert t["period"] == "Monthly" and t["label"] == "October 2026" and t["pct"] == 88.0


def test_a_weekly_total_budget_lines_up_by_weekday_and_an_annual_one_by_month():
    weekly = item(risk(late_spending("X", [100] * 5), [], period(kind="Weekly", days_remaining=4)), "Total")
    annual = item(risk(late_spending("X", [100] * 5), [], period(kind="Annual")), "Total")

    assert (weekly["align"], weekly["anchor"]) == ("week", TODAY.weekday())
    assert (annual["align"], annual["anchor"]) == ("month", TODAY.day)


def test_category_budgets_are_monthly_and_skip_the_total_row_and_empty_budgets():
    statuses = [status("Groceries", 1000, 100), status("Total", 1000, 100), status("Unused", 0, 0)]

    r = risk(late_spending("Groceries", [10] * 5), statuses)

    assert [i["category"] for i in r["items"]] == ["Groceries"]
    assert item(r, "Groceries")["period"] == "Monthly" and item(r, "Groceries")["days_remaining"] == 10


def test_a_category_with_no_spending_history_is_not_estimated():
    g = item(risk([], [status("Gifts", 500, 0)]), "Gifts")

    assert (g["available"], g["reason"], g["samples"]) == (False, "not_enough_history", 0)


def test_no_budgets_means_nothing_to_show():
    r = risk(late_spending("Groceries", [10] * 5))

    assert r["has_budgets"] is False and r["items"] == []


def test_riskiest_first_then_the_unestimated_last_and_equal_chances_in_alphabetical_order():
    rows = late_spending("Safe", [1] * 6) + late_spending("Risky", [900] * 6) + late_spending("Tie", [900] * 6)
    statuses = [status("Safe", 1000, 900), status("Risky", 1000, 900), status("Tie", 1000, 900), status("New", 500, 10), status("Over", 100, 300)]

    r = risk(rows, statuses, period(effective=1000, spent=900, projected=900))

    assert [(i["category"], i["probability"]) for i in r["items"]] == [
        ("Over", 100.0), ("Risky", 92.9), ("Tie", 92.9), ("Total", 91.7), ("Safe", 7.1), ("New", None)]


def test_the_total_comes_before_a_category_with_exactly_the_same_chance():
    # All spending is in one category, so the two series are identical. (Recording starts on the 22nd, the first
    # day of the window, so the total keeps its first month too.)
    rows = late_spending("Only", [900] * 6, day=22)

    r = risk(rows, [status("Only", 1000, 900)], period(effective=1000, spent=900, projected=900))

    assert [i["category"] for i in r["items"]] == ["Total", "Only"]
    assert r["items"][0]["probability"] == r["items"][1]["probability"]


# --- awkward rows ------------------------------------------------------------------------------

def test_future_dated_zero_and_unreadable_rows_are_ignored_and_inputs_untouched():
    rows = late_spending("Groceries", [100] * 5) + [
        row("2026-10-25", "Groceries", 99999), row("2026-09-29", "Groceries", 0), row("2026-09-29", "Groceries", -50),
        {"date": None, "category": "Groceries", "amount": D(5)}, {"date": "garbage", "category": "Groceries", "amount": D(5)},
        {"date": "2026-08-30", "category": "Groceries", "amount": "7.5"},
    ]
    before = [dict(r) for r in rows]

    g = item(risk(rows, [status("Groceries", 1000, 950)]), "Groceries")

    assert rows == before
    assert g["typical_remaining"] == D("100.00") and g["samples"] == 5


def test_the_result_is_explained_for_the_ui():
    r = risk(late_spending("Groceries", [100] * 5), [status("Groceries", 1000, 900)], period())

    assert set(r) == {"today", "has_budgets", "items", "min_periods", "alert_threshold"}
    assert (r["min_periods"], r["alert_threshold"], r["today"]) == (4, 75.0, "2026-10-21")
    assert set(r["items"][0]) == {"category", "is_total", "period", "label", "limit", "spent", "remaining", "pct", "days_remaining",
                                  "align", "anchor", "available", "reason", "probability", "level", "samples", "exceeded", "typical_remaining"}
