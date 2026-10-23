"""Forecast of this month's spending: methods, backtest, range, and how it is built from expenses."""
import datetime as dt
import math
from decimal import Decimal as D

import pytest

from app.logic import forecast as fc

TODAY = dt.date(2026, 10, 21)  # the month in progress is October 2026


def e(date, category, amount, **extra):
    return {"id": None, "date": dt.date.fromisoformat(date), "category": category, "amount": D(str(amount)),
            "description": extra.pop("description", category), **extra}


def monthly(values, start="2025-01", category="Food", day=5, **extra):
    """One expense per month, oldest first, with the given amounts."""
    year, month = int(start[:4]), int(start[5:7])
    rows = []
    for i, v in enumerate(values):
        index = year * 12 + month - 1 + i
        rows.append(e(f"{index // 12}-{index % 12 + 1:02d}-{day:02d}", category, v, **extra))
    return rows


def run(rows, **kw):
    return fc.forecast(rows, today=TODAY, **kw)


# --- the methods ------------------------------------------------------------------------------

def test_the_simplest_methods():
    assert fc._naive([1, 2, 3]) == 3
    assert fc._mean3([1, 2, 3, 4]) == 3.0
    assert fc._mean3([5]) == 5 and fc._mean3([4, 6]) == 5


def test_smoothing_stays_within_the_data_and_leans_on_recent_months():
    assert fc._ses([100.0] * 6) == pytest.approx(100.0)
    stepped = fc._ses([10.0, 10.0, 10.0, 20.0, 20.0, 20.0])
    assert 10 < stepped <= 20 and stepped > 15  # closer to the recent 20s than to the old 10s


def test_the_trend_method_follows_a_rise_but_lets_it_fade():
    y = [100.0, 110.0, 120.0, 130.0, 140.0, 150.0]

    f = fc._holt_damped(y)

    assert 150 < f < 160  # keeps climbing, but short of the undamped 160
    assert fc._holt_damped([100.0] * 6) == pytest.approx(100.0)


def test_nothing_is_ever_forecast_below_zero():
    assert fc._predict("holt", [900.0, 500.0, 100.0, 10.0, 0.0]) >= 0
    assert fc._predict("naive", [5.0, 0.0]) == 0.0


def test_seasonal_repeats_the_same_month_last_year():
    y = [100.0 if m % 12 != 11 else 250.0 for m in range(35)]  # Jan year 1 .. Nov year 3; next is December

    assert fc._seasonal(y) == pytest.approx(250.0)


def test_seasonal_scales_by_recent_levels_within_limits():
    y = [100.0] * 35
    y[-3:] = [1000.0, 1000.0, 1000.0]                      # recent months ten times a year ago

    assert fc._seasonal(y) == pytest.approx(100.0 * fc.SEASONAL_RATIO_LIMITS[1])


# --- testing the methods ---------------------------------------------------------------------

def test_the_error_measures_are_what_they_say():
    m = fc._metrics([(100, 90), (110, 120), (100, 100)])  # errors +10, -10, 0

    assert m["rmse"] == pytest.approx(math.sqrt(200 / 3))
    assert m["mae"] == pytest.approx(20 / 3)
    assert m["bias"] == pytest.approx(0.0)
    assert m["mape"] == pytest.approx((0.1 + 10 / 110 + 0) / 3 * 100)


def test_months_with_no_spending_are_left_out_of_the_percentage_error():
    assert fc._metrics([(0, 5), (100, 90)])["mape"] == pytest.approx(10.0)
    assert fc._metrics([(0, 5), (0, 1)])["mape"] is None


def test_a_positive_bias_means_spending_came_in_above_the_forecast():
    assert fc._metrics([(120, 100), (130, 100)])["bias"] > 0


def test_the_simpler_method_is_kept_unless_the_other_is_clearly_better():
    mk = lambda *rmses: [{"name": n, "rmse": r} for n, r in zip(("naive", "mean3", "ses", "holt"), rmses)]

    assert fc._choose(mk(10, 9.6, 9.7, 9.8))["name"] == "naive"          # nobody 5% better
    assert fc._choose(mk(10, 9.4, 9.3, 9.2))["name"] == "mean3"          # mean3 clears 5%, others don't beat *it* by 5%
    assert fc._choose(mk(10, 9.0, 8.0, 7.8))["name"] == "ses"            # a second step needs another 5%


def test_the_range_widens_for_fewer_tests_and_settles_to_the_normal_value():
    assert fc.t_multiplier(3) == 1.638 and fc.t_multiplier(6) == 1.44 and fc.t_multiplier(30) == 1.31
    assert fc.t_multiplier(31) == fc.t_multiplier(500) == 1.2816
    assert all(fc.t_multiplier(n) > fc.t_multiplier(n + 1) for n in range(1, 30))


def test_the_t_values_match_scipy():
    stats = pytest.importorskip("scipy.stats")

    for df in range(1, 31):
        assert fc.t_multiplier(df) == pytest.approx(stats.t.ppf(0.9, df), abs=0.001)
    assert fc._Z80 == pytest.approx(stats.norm.ppf(0.9), abs=0.0001)


# --- fitting a series ------------------------------------------------------------------------

def test_a_series_needs_three_months():
    assert fc._fit([100.0, 100.0]) is None and fc._fit([]) is None


def test_three_or_four_months_give_a_number_but_no_test_and_no_range():
    f = fc._fit([100.0, 200.0, 300.0, 400.0])

    assert f["model"] == "mean3" and f["point"] == pytest.approx(300.0)
    assert f["tests"] == 0 and f["accuracy"] is None and f["interval"] is None and f["results"] == []


def test_five_or_six_months_are_tested_but_too_few_for_a_range():
    for n in (5, 6):
        f = fc._fit([100.0, 120.0, 90.0, 110.0, 100.0, 105.0][:n])
        assert f["tests"] == n - fc.MIN_TRAIN and f["accuracy"]["months_tested"] == n - fc.MIN_TRAIN
        assert f["interval"] is None and f["model"] == "mean3"


def test_seven_months_give_a_range_from_the_methods_own_errors():
    y = [100.0, 110.0, 100.0, 110.0, 100.0, 110.0, 100.0]          # n=7: tests the last 3

    f = fc._fit(y)

    by = {r["name"]: r for r in f["results"]}
    assert f["tests"] == 3
    assert by["naive"]["rmse"] == pytest.approx(10.0) and by["naive"]["mae"] == pytest.approx(10.0)
    assert by["naive"]["bias"] == pytest.approx(-10 / 3) and by["naive"]["mape"] == pytest.approx((0.1 + 10 / 110 + 0.1) / 3 * 100)
    assert by["mean3"]["rmse"] == pytest.approx(20 / 3)                    # off by 6.67 each time
    chosen = next(r for r in f["results"] if r["name"] == f["model"])
    assert chosen["rmse"] <= by["mean3"]["rmse"] + 1e-9                    # never worse than the simpler methods
    half = fc.t_multiplier(3) * chosen["rmse"]
    assert f["interval"] == pytest.approx((max(0.0, f["point"] - half), f["point"] + half))


def test_a_perfectly_steady_series_has_no_range_and_keeps_the_simplest_method():
    f = fc._fit([500.0] * 10)

    assert f["model"] == "naive" and f["point"] == 500.0
    assert f["interval"] == (500.0, 500.0)
    assert f["accuracy"]["mape"] == 0.0 and f["accuracy"]["beats_naive"] is None


def test_the_lower_end_of_the_range_is_never_below_zero():
    f = fc._fit([0.0, 400.0, 0.0, 400.0, 0.0, 400.0, 10.0])

    assert f["interval"][0] == 0.0 and f["interval"][1] > f["point"]


def test_a_steady_rise_makes_forecasts_run_low_so_bias_is_positive():
    f = fc._fit([100.0 + 20 * i for i in range(10)])

    chosen = next(r for r in f["results"] if r["name"] == f["model"])
    assert chosen["bias"] > 0 and f["accuracy"]["bias"] > 0


def test_seasonal_memory_is_only_considered_with_enough_history():
    short = fc._fit([100.0 + (i % 5) for i in range(fc.SEASONAL_MIN_MONTHS - 1)])
    enough = fc._fit([100.0 + (i % 5) for i in range(fc.SEASONAL_MIN_MONTHS)])

    assert not short["seasonal_considered"] and "seasonal" not in {r["name"] for r in short["results"]}
    assert short["tests"] == fc.MAX_BACKTEST
    assert enough["seasonal_considered"] and "seasonal" in {r["name"] for r in enough["results"]}
    assert enough["tests"] == fc.MAX_BACKTEST_SEASONAL                     # long enough to test every season


# --- building it from expenses ---------------------------------------------------------------

def test_nothing_recorded_is_unavailable_with_the_reason():
    r = run([])

    assert r["available"] is False and r["reason"] == "no_spending" and r["months_available"] == 0
    assert r["requirements"] == {"min_months": 3, "months_to_test": 5, "months_for_range": 7, "months_for_seasons": 27}


def test_too_little_history_says_how_much_there_is():
    only_this_month = run([e("2026-10-02", "Food", 50)])
    two_months = run(monthly([100, 120], start="2026-08"))

    assert (only_this_month["available"], only_this_month["reason"], only_this_month["months_available"]) == (False, "not_enough_history", 0)
    assert (two_months["available"], two_months["reason"], two_months["months_available"]) == (False, "not_enough_history", 2)


def test_three_finished_months_give_a_number_without_a_range():
    r = run(monthly([300, 600, 900], start="2026-07"))

    assert r["available"] is True and r["month"] == "2026-10" and r["months_available"] == 3
    assert r["forecast"] == {"point": D("600.00"), "low": None, "high": None}
    assert r["accuracy"] is None and r["candidates"] == []
    assert r["model"]["name"] == "mean3"


def test_a_range_and_a_track_record_from_seven_months():
    r = run(monthly([1000, 1100, 1000, 1100, 1000, 1100, 1000], start="2026-03"))

    assert r["months_available"] == 7
    f = r["forecast"]
    assert f["low"] is not None and f["low"] <= f["point"] <= f["high"]
    assert r["accuracy"]["months_tested"] == 3 and r["accuracy"]["naive_mape"] == pytest.approx(9.7, abs=0.05)
    assert {c["name"] for c in r["candidates"]} >= {"naive", "mean3", "ses", "holt"}
    assert sum(1 for c in r["candidates"] if c["chosen"]) == 1


def test_the_month_in_progress_is_not_part_of_the_series_but_is_reported_so_far():
    rows = monthly([1000, 1000, 1000, 1000], start="2026-06") + [e("2026-10-03", "Food", 9999)]

    r = run(rows)

    assert r["forecast"]["point"] == D("1000.00")                           # October's 9,999 doesn't drag it
    assert r["so_far"]["total"] == D("9999.00") and r["so_far"]["day"] == 21
    assert r["history"][-1]["month"] == "2026-09"


def test_spending_dated_after_today_is_ignored():
    rows = monthly([500, 500, 500], start="2026-07") + [e("2026-10-22", "Food", 99999)]

    r = run(rows)

    assert r["so_far"]["total"] == D("0.00")


def test_nothing_is_forecast_below_zero():
    rows = monthly([900, 500, 100, 10, 1, 1, 1], start="2026-03")

    r = run(rows)

    assert r["forecast"]["point"] >= 0 and r["forecast"]["low"] >= 0


# --- one-offs stay out of the baseline --------------------------------------------------------

def ordinary_groceries(n=9, start="2026-01"):
    return [e(f"{r['date'].isoformat()}", "Groceries", r["amount"]) for r in monthly([100 + 10 * (i % 4) for i in range(n)], start=start, category="Groceries")]


def test_a_one_off_does_not_inflate_the_forecast_and_is_reported_beside_it():
    plain = run(ordinary_groceries())
    spiked = run(ordinary_groceries() + [e("2026-06-20", "Groceries", 3000, description="Party")])

    assert spiked["forecast"] == plain["forecast"]                          # baseline is unchanged
    june = next(m for m in spiked["history"] if m["month"] == "2026-06")
    assert june["one_off"] == D("3000.00") and june["baseline"] == plain["history"][5]["baseline"]
    assert june["total"] == june["baseline"] + june["one_off"]
    o = spiked["one_offs"]
    assert o["months_with_one_offs"] == 1 and o["window_months"] == 9
    assert o["average_per_month"] == D("333.33") and o["with_one_offs"] == spiked["forecast"]["point"] + o["average_per_month"]


def test_one_offs_this_month_are_separated_in_so_far():
    rows = ordinary_groceries() + [e("2026-10-04", "Groceries", 4000, description="Fridge"), e("2026-10-05", "Groceries", 110)]

    r = run(rows)

    assert r["so_far"] == {"day": 21, "total": D("4110.00"), "baseline": D("110.00"), "one_off": D("4000.00")}


def test_committed_payments_count_as_baseline():
    rows = monthly([9000] * 5, start="2026-05", category="Housing", recurring_template_id=1)

    r = run(rows)

    assert r["forecast"]["point"] == D("9000.00") and r["one_offs"]["average_per_month"] == D("0.00")
    assert [c["category"] for c in r["categories"]] == ["Housing"]


# --- which months are used --------------------------------------------------------------------

def test_a_first_month_that_began_part_way_through_is_not_a_full_month():
    started_late = monthly([100, 100, 100, 100], start="2026-06", day=20)       # recording began on the 20th
    started_early = monthly([100, 100, 100, 100], start="2026-06", day=10)       # on the 10th: counts

    late, early = run(started_late), run(started_early)

    assert late["skipped_first_month"] is True and late["months_available"] == 3
    assert early["skipped_first_month"] is False and early["months_available"] == 4
    assert run(monthly([100] * 4, start="2026-06", day=11))["skipped_first_month"] is True


def test_quiet_months_between_are_zero_not_missing():
    rows = monthly([500, 500], start="2026-04") + monthly([500, 500, 500], start="2026-07")   # nothing in June

    r = run(rows)

    assert r["months_available"] == 6
    assert [m["baseline"] for m in r["history"]][:3] == [D("500.00"), D("500.00"), D("0.00")]


def test_only_the_last_36_months_are_used_and_the_chart_shows_12():
    rows = monthly([100 + (i % 3) for i in range(40)], start="2023-06", day=5)

    r = run(rows)

    assert r["months_available"] == fc.MAX_HISTORY and len(r["history"]) == fc.CHART_MONTHS
    assert r["history"][-1]["month"] == "2026-09"


def test_rows_that_cannot_be_used_are_ignored_and_inputs_are_not_modified():
    rows = monthly([300, 300, 300, 300], start="2026-06") + [
        {"date": None, "category": "Food", "amount": D(5)}, {"date": "garbage", "category": "Food", "amount": D(5)},
        e("2026-08-02", "Food", 0), e("2026-08-02", "Food", -50), {"date": "2026-09-03", "category": "Food", "amount": "7.5"},
    ]
    before = [dict(r) for r in rows]

    r = run(rows)

    assert rows == before
    assert next(m for m in r["history"] if m["month"] == "2026-09")["baseline"] == D("307.50")   # text date and amount are fine


def test_the_same_input_always_gives_the_same_answer():
    rows = ordinary_groceries() + [e("2026-06-20", "Groceries", 3000)]

    assert run(rows) == run(list(reversed(rows)))


# --- seasons ----------------------------------------------------------------------------------

def test_a_yearly_pattern_is_used_once_there_is_enough_history():
    values = [250 if m % 12 == 11 else 100 for m in range(35)]                  # a December spike each year
    today = dt.date(2028, 12, 10)

    r = fc.forecast(monthly(values, start="2026-01"), today=today)

    assert r["months_available"] == 35 and r["model"]["seasonal_considered"] is True
    assert r["model"]["name"] == "seasonal" and r["forecast"]["point"] == D("250.00")
    assert r["accuracy"]["months_tested"] == fc.MAX_BACKTEST_SEASONAL
    chosen = next(c for c in r["candidates"] if c["chosen"])
    naive = next(c for c in r["candidates"] if c["name"] == "naive")
    assert chosen["rmse"] < naive["rmse"]


def test_without_enough_history_seasons_are_not_considered():
    r = run(monthly([250 if m % 12 == 11 else 100 for m in range(20)], start="2025-01"))

    assert r["model"]["seasonal_considered"] is False and "seasonal" not in {c["name"] for c in r["candidates"]}


# --- categories ------------------------------------------------------------------------------

def categories_dataset():
    rows = []
    for name, values in (("Housing", [3000, 3100, 2900, 3000, 3050, 2950, 3000]), ("Food", [1000, 900, 1100, 1000, 950, 1050, 1000]),
                         ("Fun", [333, 334, 333, 333, 334, 333, 333])):
        rows += monthly(values, start="2026-03", category=name)
    return rows


def test_the_category_forecasts_add_up_to_the_total_exactly():
    r = run(categories_dataset())

    assert sum(c["forecast"] for c in r["categories"]) == r["forecast"]["point"]
    assert [c["category"] for c in r["categories"]] == ["Housing", "Food", "Fun"]       # biggest first
    assert all(c["forecast"] >= 0 for c in r["categories"])
    assert sum(c["share_pct"] for c in r["categories"]) == pytest.approx(100, abs=0.2)


def test_cent_rounding_never_makes_the_categories_miss_the_total():
    # Scaling each category to the total and rounding to cents drifts by a cent for this data
    # (1,073.93 against 1,073.92) unless the remainder is absorbed.
    data = {"A": [862.63, 855.65, 98.07, 122.14, 760.17, 675.57, 619.27],
            "B": [311.92, 565.05, 565.78, 544.02, 184.63, 416.07, 384.5],
            "C": [664.56, 895.6, 856.99, 512.55, 428.13, 278.0, 80.54]}
    rows = [row for name, values in data.items() for row in monthly(values, start="2026-03", category=name)]

    r = run(rows)

    assert r["forecast"]["point"] == D("1073.92")
    assert sum(c["forecast"] for c in r["categories"]) == D("1073.92")


def test_each_category_shows_last_month_and_the_change():
    r = run(categories_dataset())

    housing = next(c for c in r["categories"] if c["category"] == "Housing")
    assert housing["last_month"] == D("3000.00") and housing["change"] == housing["forecast"] - housing["last_month"]


def test_small_categories_are_rolled_into_one_line_listed_last_and_still_add_up():
    rows = []
    for i in range(8):
        rows += monthly([1000 - i * 100] * 6, start="2026-04", category=f"Cat{i}")

    r = run(rows, top=3)

    names = [c["category"] for c in r["categories"]]
    assert names == ["Cat0", "Cat1", "Cat2", fc.ROLLUP]            # the roll-up is biggest (1,500) but still last
    assert [c["rollup"] for c in r["categories"]] == [False, False, False, True]
    assert sum(c["forecast"] for c in r["categories"]) == r["forecast"]["point"]
    # Each category is steady, so each forecast is its own amount; the five smallest add up to 2,500.
    assert [c["forecast"] for c in r["categories"]] == [D("1000.00"), D("900.00"), D("800.00"), D("2500.00")]
    assert r["forecast"]["point"] == D("5200.00")


def test_the_roll_up_does_not_swallow_a_real_category_with_a_similar_name():
    rows = monthly([500] * 6, start="2026-04", category="Other")
    for i in range(3):
        rows += monthly([200 + i] * 6, start="2026-04", category=f"Small{i}")

    r = run(rows, top=2)

    names = [c["category"] for c in r["categories"]]
    assert "Other" in names and fc.ROLLUP in names and names[-1] == fc.ROLLUP


def test_without_a_roll_up_nothing_is_marked_as_one():
    r = run(monthly([300] * 5, start="2026-05", category="Food"))

    assert [c["rollup"] for c in r["categories"]] == [False]


def test_a_category_with_no_recent_spending_is_left_out():
    rows = monthly([500] * 8, start="2026-01", category="Food") + monthly([100, 100], start="2026-01", category="Old hobby")

    r = run(rows)

    assert [c["category"] for c in r["categories"]] == ["Food"]


def test_blank_categories_are_grouped_as_uncategorised():
    r = run(monthly([200] * 5, start="2026-05", category=""))

    assert [c["category"] for c in r["categories"]] == ["Uncategorised"]


def test_the_result_is_explained_for_the_ui():
    r = run(monthly([1000, 1100, 1000, 1100, 1000, 1100, 1000], start="2026-03"))

    assert r["level"] == 80 and r["model"]["label"]
    assert set(r) >= {"available", "reason", "month", "requirements", "level", "months_available", "skipped_first_month", "forecast", "model",
                      "accuracy", "candidates", "so_far", "one_offs", "history", "categories"}
    assert set(r["accuracy"]) == {"months_tested", "mape", "mae", "bias", "naive_mape", "beats_naive"}
