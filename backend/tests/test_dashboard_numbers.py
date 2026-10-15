"""Release 9: partial current month must not skew MoM/forecast; categorizer matches whole words."""
from datetime import date
from decimal import Decimal

import pytest

from app.logic import analytics, categorizer

D = Decimal
OCT7 = date(2026, 10, 7)


def m(month, total):
    return {"month": month, "total": D(str(total))}


def test_partial_month_is_excluded_from_change():
    monthly = [m("2026-08", 5000), m("2026-09", 5100), m("2026-10", 600)]
    ch = analytics.month_over_month_change(monthly, OCT7)
    assert ch["last_month"] == "2026-09" and ch["previous_month"] == "2026-08"
    assert ch["pct_change"] == 2.0 and ch["direction"] == "up"


def test_change_needs_two_finished_months():
    assert analytics.month_over_month_change([m("2026-09", 100), m("2026-10", 5)], OCT7) is None
    assert analytics.month_over_month_change([], OCT7) is None


def test_gap_month_counts_as_zero_not_skipped():
    monthly = [m("2026-07", 1000), m("2026-09", 500)]
    ch = analytics.month_over_month_change(monthly, OCT7)
    assert ch["previous_month"] == "2026-08" and ch["previous"] == 0
    assert ch["pct_change"] is None and ch["direction"] == "up"


def test_last_month_without_spend_is_minus_100():
    ch = analytics.month_over_month_change([m("2026-08", 400), m("2026-09", 400)], date(2026, 11, 3))
    assert ch["last"] == 0 and ch["pct_change"] == -100.0


@pytest.mark.skipif(not analytics.HAS_STATS, reason="statsmodels missing")
def test_forecast_ignores_partial_month_and_is_not_negative():
    monthly = [m("2026-07", 5000), m("2026-08", 5000), m("2026-09", 5100), m("2026-10", 600)]
    f = analytics.forecast_next_month(monthly, OCT7)
    assert f is not None and f > 4500
    declining = [m("2026-05", 900), m("2026-06", 500), m("2026-07", 100), m("2026-08", 10)]
    assert analytics.forecast_next_month(declining, date(2026, 9, 5)) >= 0


def test_forecast_needs_three_finished_months():
    monthly = [m("2026-08", 5000), m("2026-09", 5100), m("2026-10", 600)]
    assert analytics.forecast_next_month(monthly, OCT7) is None


def test_complete_months_drops_current_month():
    exp = [
        {"date": "2026-08-10", "amount": 1000, "category": "x"},
        {"date": "2026-09-10", "amount": 1000, "category": "x"},
        {"date": "2026-10-02", "amount": 5, "category": "x"},
    ]
    done = analytics.complete_months(analytics.monthly_totals(exp), OCT7)
    assert [x["month"] for x in done] == ["2026-08", "2026-09"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Pizza slice", "Dining"),
        ("Steak", None),
        ("Parent teacher conference fee", None),
        ("Barnes & Noble gift", None),
        ("Slow cooker", None),
        ("Bus ticket", "Transport"),
        ("SL monthly card", "Transport"),
        ("ICA Maxi", "Groceries"),
        ("Eggs and milk", "Groceries"),
        ("Netflix", "Entertainment"),
        ("H&M jacket", "Shopping"),
        ("booking.com hotel", "Travel"),
        ("Apoteket", "Healthcare"),
    ],
)
def test_categorizer_whole_words(text, expected):
    assert categorizer.categorize_by_rules(text) == expected
