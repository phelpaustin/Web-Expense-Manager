"""Category change attribution: which categories explain the change versus last month."""
import datetime as dt
from decimal import Decimal as D

import pytest

from app.logic import category_change as cc

TODAY = dt.date(2026, 10, 16)  # the month in progress is October 2026


def e(date, category, amount):
    return {"date": dt.date.fromisoformat(date), "category": category, "amount": D(str(amount))}


SEPT_VS_AUG = [
    e("2026-08-03", "Groceries", 1000), e("2026-08-20", "Dining", 200),
    e("2026-09-02", "Groceries", 1800), e("2026-09-10", "Dining", 500), e("2026-09-12", "Transport", 100),
]


def by_category(result):
    return {c["category"]: c for c in result["categories"]}


# --- the headline: the drivers of the change ---------------------------------------------

def test_explains_the_change_by_category_biggest_mover_first():
    r = cc.category_change(SEPT_VS_AUG, "2026-09", today=TODAY)

    assert (r["month"], r["compare_month"], r["partial"], r["available"]) == ("2026-09", "2026-08", False, True)
    assert r["total"] == {"now": D("2400.00"), "before": D("1200.00"), "change": D("1200.00"), "pct_change": 100.0, "direction": "up"}
    assert [(c["category"], c["change"]) for c in r["categories"]] == [
        ("Groceries", D("800.00")), ("Dining", D("300.00")), ("Transport", D("100.00")),
    ]
    assert r["other"] is None


def test_the_category_changes_always_add_up_to_the_total_change():
    rows = [e("2026-08-01", f"C{i}", 100 + i * 7) for i in range(12)] + [e("2026-09-01", f"C{i}", 90 + i * 11) for i in range(12)]
    rows += [e("2026-09-02", "Brand new", "33.33"), e("2026-08-02", "Gone", "12.34")]

    r = cc.category_change(rows, "2026-09", today=TODAY, top=4)

    assert len(r["categories"]) == 4 and r["other"]["count"] == 10  # 14 movers: 4 shown + 10 rolled up
    shown = sum(c["change"] for c in r["categories"])
    assert shown + r["other"]["change"] == r["total"]["change"]
    assert sum(c["now"] for c in r["categories"]) + r["other"]["now"] == r["total"]["now"]
    assert sum(c["before"] for c in r["categories"]) + r["other"]["before"] == r["total"]["before"]


def test_a_fall_is_attributed_too_and_movers_are_ranked_by_size_not_direction():
    rows = [e("2026-08-01", "Groceries", 2000), e("2026-08-02", "Dining", 300),
            e("2026-09-01", "Groceries", 1500), e("2026-09-02", "Dining", 400)]

    r = cc.category_change(rows, "2026-09", today=TODAY)

    assert r["total"]["change"] == D("-400.00") and r["total"]["direction"] == "down"
    assert [(c["category"], c["change"]) for c in r["categories"]] == [("Groceries", D("-500.00")), ("Dining", D("100.00"))]


def test_new_and_stopped_categories_are_labelled_and_have_no_percentage_when_new():
    rows = [e("2026-08-01", "Gym", 300), e("2026-08-02", "Food", 100), e("2026-09-01", "Travel", 800), e("2026-09-02", "Food", 100)]

    got = by_category(cc.category_change(rows, "2026-09", today=TODAY))

    assert (got["Travel"]["status"], got["Travel"]["pct_change"]) == ("new", None)
    assert (got["Gym"]["status"], got["Gym"]["pct_change"]) == ("stopped", -100.0)
    assert "Food" not in got  # unchanged: left out


def test_unchanged_categories_are_counted_not_listed():
    rows = [e("2026-08-01", "Food", 100), e("2026-09-01", "Food", 100), e("2026-08-02", "Rent", 900), e("2026-09-02", "Rent", 900),
            e("2026-09-03", "Fun", 50)]

    r = cc.category_change(rows, "2026-09", today=TODAY)

    assert [c["category"] for c in r["categories"]] == ["Fun"]
    assert r["unchanged_count"] == 2


def test_ties_are_broken_alphabetically_so_the_order_is_stable():
    rows = [e("2026-09-01", "Bravo", 50), e("2026-09-01", "Alpha", 50), e("2026-09-01", "Charlie", 50)]

    r = cc.category_change(rows, "2026-09", today=TODAY)

    assert [c["category"] for c in r["categories"]] == ["Alpha", "Bravo", "Charlie"]


# --- the month in progress is compared like for like ----------------------------------

def test_the_month_in_progress_is_compared_with_the_same_days_of_last_month():
    rows = [
        e("2026-09-05", "Food", 100), e("2026-09-16", "Food", 50),
        e("2026-09-17", "Food", 5000), e("2026-09-30", "Food", 5000),   # after the 16th: not comparable yet
        e("2026-10-05", "Food", 120), e("2026-10-16", "Food", 80),
    ]

    r = cc.category_change(rows, "2026-10", today=TODAY)

    assert (r["partial"], r["through_day"]) == (True, 16)
    assert r["total"]["before"] == D("150.00") and r["total"]["now"] == D("200.00") and r["total"]["change"] == D("50.00")


def test_a_finished_month_is_never_cut_short():
    rows = [e("2026-08-30", "Food", 100), e("2026-09-30", "Food", 300)]

    r = cc.category_change(rows, "2026-09", today=TODAY)

    assert (r["partial"], r["through_day"]) == (False, None)
    assert r["total"]["change"] == D("200.00")


def test_a_shorter_previous_month_is_included_whole():
    today = dt.date(2026, 3, 31)  # February has only 28 days
    rows = [e("2026-02-01", "Food", 100), e("2026-02-28", "Food", 100), e("2026-03-01", "Food", 300)]

    r = cc.category_change(rows, "2026-03", today=today)

    assert r["total"]["before"] == D("200.00") and r["total"]["now"] == D("300.00")


def test_january_compares_with_the_december_before():
    rows = [e("2025-12-20", "Food", 100), e("2026-01-05", "Food", 150)]

    r = cc.category_change(rows, "2026-01", today=TODAY)

    assert r["compare_month"] == "2025-12" and r["total"]["change"] == D("50.00")


# --- awkward data ------------------------------------------------------------------------

def test_nothing_in_either_month_is_unavailable_not_an_error():
    r = cc.category_change([e("2026-01-05", "Food", 10)], "2026-09", today=TODAY)

    assert r["available"] is False and r["categories"] == [] and r["other"] is None
    assert r["total"]["change"] == D("0.00") and r["total"]["pct_change"] is None and r["total"]["direction"] == "flat"
    assert cc.category_change([], "2026-09", today=TODAY)["available"] is False


def test_spending_with_no_earlier_month_is_all_new_with_no_percentage():
    r = cc.category_change([e("2026-09-05", "Food", 120)], "2026-09", today=TODAY)

    assert r["available"] is True and r["total"]["pct_change"] is None
    assert r["categories"][0]["status"] == "new"


def test_blank_categories_are_grouped_as_uncategorised_and_dates_may_be_text():
    rows = [{"date": "2026-08-05", "category": "", "amount": 10}, {"date": "2026-09-05T10:00:00", "category": None, "amount": "25.555"},
            {"date": "garbage", "category": "Food", "amount": 999}, {"date": None, "category": "Food", "amount": 999}]

    r = cc.category_change(rows, "2026-09", today=TODAY)

    assert [(c["category"], c["before"], c["now"]) for c in r["categories"]] == [("Uncategorised", D("10.00"), D("25.56"))]


def test_rounding_never_breaks_the_arithmetic():
    rows = [e("2026-08-01", "A", "0.005"), e("2026-08-02", "A", "0.005"), e("2026-09-01", "A", "0.004"), e("2026-09-02", "B", "10.004")]

    r = cc.category_change(rows, "2026-09", today=TODAY)

    total = sum(c["change"] for c in r["categories"])
    assert total == r["total"]["change"]
    assert all(c["now"] - c["before"] == c["change"] for c in r["categories"])


# --- which month to explain by default ----------------------------------------------------

def test_default_month_is_the_last_finished_month():
    assert cc.default_month(SEPT_VS_AUG + [e("2026-10-02", "Food", 5)], today=TODAY) == "2026-09"


def test_default_month_falls_back_to_the_month_in_progress_when_nothing_has_finished():
    assert cc.default_month([e("2026-10-02", "Food", 5)], today=TODAY) == "2026-10"
    assert cc.default_month([], today=TODAY) == "2026-10"


def test_default_month_is_a_quiet_last_month_just_as_the_dashboard_change_is():
    rows = [e("2026-07-02", "Food", 50), e("2026-08-02", "Food", 60)]  # nothing in September

    r = cc.category_change(rows, cc.default_month(rows, today=TODAY), today=TODAY)

    assert r["month"] == "2026-09" and r["total"]["now"] == D("0.00") and r["total"]["change"] == D("-60.00")


def test_months_lists_every_month_with_spending_oldest_first():
    assert cc.category_change(SEPT_VS_AUG, "2026-09", today=TODAY)["months"] == ["2026-08", "2026-09"]


def test_the_default_matches_the_existing_month_over_month_figure():
    """The headline total must be the same change the dashboard already shows."""
    from app.logic import analytics

    rows = SEPT_VS_AUG + [e("2026-07-10", "Food", 77)]
    mom = analytics.month_over_month_change(analytics.monthly_totals(rows), TODAY)

    r = cc.category_change(rows, cc.default_month(rows, TODAY), today=TODAY)

    assert (r["month"], r["compare_month"]) == (mom["last_month"], mom["previous_month"])
    assert (r["total"]["now"], r["total"]["before"]) == (mom["last"], mom["previous"])
