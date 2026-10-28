"""Yearly and monthly report logic."""
import datetime as dt
from decimal import Decimal as D

from app.logic import report as rp

TODAY = dt.date(2026, 10, 28)
_ids = iter(range(1, 100_000))


def e(date, amount, category="Food", description="x", shop="", **extra):
    return {"id": next(_ids), "date": dt.date.fromisoformat(date), "category": category, "description": description, "shop": shop,
            "amount": D(str(amount)), **extra}


def inc(date, amount):
    return {"date": dt.date.fromisoformat(date), "amount": D(str(amount))}


def year(rows, income=None, y=2026, **kw):
    return rp.build_report(rows, income, y, None, today=kw.pop("today", TODAY))


def month(rows, income=None, y=2026, m=10, **kw):
    return rp.build_report(rows, income, y, m, today=kw.pop("today", TODAY))


def test_period_helpers():
    assert rp.period_label(2026, None) == "2026" and rp.period_label(2026, 3) == "March 2026"
    assert rp.period_bounds(2026, None) == (dt.date(2026, 1, 1), dt.date(2026, 12, 31))
    assert rp.period_bounds(2028, 2) == (dt.date(2028, 2, 1), dt.date(2028, 2, 29))
    assert rp.previous_period(2026, None) == (2025, None)
    assert rp.previous_period(2026, 3) == (2026, 2) and rp.previous_period(2026, 1) == (2025, 12)


def test_a_year_report_covers_only_that_year():
    r = year([e("2025-12-31", 1000), e("2026-01-01", 10), e("2026-12-31", 20), e("2027-01-01", 5000)])
    assert (r["kind"], r["label"], r["start"], r["end"]) == ("year", "2026", "2026-01-01", "2026-12-31")
    assert r["totals"]["spent"] == D("30.00") and r["totals"]["count"] == 2


def test_a_month_report_covers_only_that_month():
    r = month([e("2026-09-30", 1000), e("2026-10-01", 10), e("2026-10-31", 20), e("2026-11-01", 5000)])
    assert (r["kind"], r["label"], r["start"], r["end"]) == ("month", "October 2026", "2026-10-01", "2026-10-31")
    assert r["totals"]["spent"] == D("30.00") and r["totals"]["count"] == 2


def test_categories_with_amount_count_and_share_largest_first():
    r = year([e("2026-02-01", 300, "Food"), e("2026-03-01", 100, "Travel"), e("2026-04-01", 100, "Food"), e("2026-04-02", 500, "Rent")])
    assert [(c["category"], c["total"], c["count"], c["share_pct"]) for c in r["categories"]] == [
        ("Rent", D("500.00"), 1, 50.0), ("Food", D("400.00"), 2, 40.0), ("Travel", D("100.00"), 1, 10.0)]


def test_categories_that_differ_only_in_case_or_spacing_are_one():
    r = year([e("2026-02-01", 10, "food"), e("2026-02-02", 10, "Food "), e("2026-02-03", 10, "Food"), e("2026-02-04", 5, " FOOD")])
    assert [(c["category"], c["total"]) for c in r["categories"]] == [("Food", D("35.00"))]


def test_an_expense_with_no_category_is_uncategorised():
    r = year([e("2026-02-01", 10, ""), e("2026-02-02", 5, None)])
    assert [(c["category"], c["total"]) for c in r["categories"]] == [("Uncategorised", D("15.00"))]


def test_a_year_is_split_into_12_months_and_names_its_peak():
    r = year([e("2026-01-15", 10), e("2026-03-02", 50), e("2026-03-30", 25), e("2026-12-01", 7)])
    assert [p["key"] for p in r["periods"]] == [f"2026-{m:02d}" for m in range(1, 13)]
    assert [p["label"] for p in r["periods"]][:3] == ["Jan", "Feb", "Mar"]
    assert [p["total"] for p in r["periods"]][:3] == [D("10.00"), D("0.00"), D("75.00")]
    assert [p["count"] for p in r["periods"]][2] == 2
    assert r["peak"] == {"key": "2026-03", "label": "March", "total": D("75.00")}


def test_a_month_is_split_into_days_and_names_its_peak():
    r = month([e("2026-10-03", 10), e("2026-10-12", 90), e("2026-10-12", 10), e("2026-10-31", 1)])
    assert len(r["periods"]) == 31 and r["periods"][0]["key"] == "2026-10-01" and r["periods"][30]["label"] == "31"
    assert r["periods"][11]["total"] == D("100.00")
    assert r["peak"] == {"key": "2026-10-12", "label": "12 October", "total": D("100.00")}
    assert len(month([], m=2, y=2027)["periods"]) == 28 and len(month([], m=2, y=2028)["periods"]) == 29


def test_a_tie_for_the_peak_goes_to_the_earlier_period():
    r = year([e("2026-05-01", 10), e("2026-02-01", 10)])
    assert r["peak"]["key"] == "2026-02"


def test_no_spending_means_no_peak_and_empty_lists():
    r = year([])
    assert r["peak"] is None and r["categories"] == [] and r["top_shops"] == [] and r["largest"] == []
    assert r["totals"]["spent"] == D("0.00") and r["totals"]["count"] == 0 and r["previous"]["change_pct"] is None
    assert len(r["periods"]) == 12 and all(p["total"] == 0 for p in r["periods"])


def test_the_year_compares_with_the_year_before():
    r = year([e("2025-06-01", 200), e("2026-06-01", 250)])
    assert r["previous"] == {"label": "2025", "spent": D("200.00"), "count": 1, "change": D("50.00"), "change_pct": 25.0}
    assert year([e("2025-06-01", 200), e("2026-06-01", 100)])["previous"]["change_pct"] == -50.0


def test_the_month_compares_with_the_month_before_including_across_a_year():
    assert month([e("2026-09-10", 100), e("2026-10-10", 150)])["previous"]["label"] == "September 2026"
    jan = month([e("2025-12-20", 80), e("2026-01-05", 100)], y=2026, m=1)
    assert jan["previous"]["label"] == "December 2025" and jan["previous"]["spent"] == D("80.00") and jan["previous"]["change_pct"] == 25.0


def test_no_percentage_when_there_was_no_spending_before():
    r = year([e("2026-06-01", 50)])
    assert r["previous"]["spent"] == D("0.00") and r["previous"]["change"] == D("50.00") and r["previous"]["change_pct"] is None


def test_income_net_and_savings_rate():
    r = year([e("2026-02-01", 600)], [inc("2026-01-25", 1000), inc("2026-02-25", 1000), inc("2025-12-25", 5000)])
    t = r["totals"]
    assert (t["income"], t["net"], t["savings_rate_pct"]) == (D("2000.00"), D("1400.00"), 70.0)


def test_without_income_there_is_no_savings_rate_and_net_is_minus_spending():
    t = year([e("2026-02-01", 600)], None)["totals"]
    assert (t["income"], t["net"], t["savings_rate_pct"]) == (D("0.00"), D("-600.00"), None)
    assert year([e("2026-02-01", 600)], [])["totals"]["savings_rate_pct"] is None


def test_spending_above_income_gives_a_negative_savings_rate():
    assert year([e("2026-02-01", 150)], [inc("2026-02-01", 100)])["totals"]["savings_rate_pct"] == -50.0


def test_averages_use_the_days_and_months_that_have_passed():
    rows = [e("2026-10-05", 280)]
    t = year(rows)["totals"]                              # today is 28 Oct: 301 days and 10 months so far
    assert t["avg_per_day"] == (D(280) / 301).quantize(D("0.01")) and t["avg_per_month"] == D("28.00")
    assert month(rows)["totals"]["avg_per_day"] == D("10.00") and month(rows)["totals"]["avg_per_month"] is None


def test_a_past_period_averages_over_all_its_days_and_a_future_one_over_none():
    past = year([e("2025-06-01", 365)], y=2025)["totals"]
    assert past["avg_per_day"] == D("1.00") and past["avg_per_month"] == (D(365) / 12).quantize(D("0.01"))
    future = year([e("2027-06-01", 365)], y=2027)["totals"]
    assert future["avg_per_day"] == D("0.00") and future["avg_per_month"] == D("0.00")
    assert month([e("2026-09-10", 300)], m=9)["totals"]["avg_per_day"] == D("10.00")


def test_a_year_has_a_category_by_month_table_a_month_does_not():
    r = year([e("2026-01-10", 10, "Food"), e("2026-01-20", 5, "Food"), e("2026-03-01", 100, "Rent"), e("2026-03-02", 1, "Food")])
    m = r["category_matrix"]
    assert m["columns"][0] == "2026-01" and len(m["columns"]) == 12
    assert [x["category"] for x in m["rows"]] == ["Rent", "Food"]                       # same order as the categories
    rent, food = m["rows"]
    assert rent["values"][2] == D("100.00") and rent["total"] == D("100.00") and sum(rent["values"]) == D("100.00")
    assert food["values"][:3] == [D("15.00"), D("0.00"), D("1.00")] and food["total"] == D("16.00")
    assert month([e("2026-10-01", 1)])["category_matrix"] is None


def test_the_matrix_rows_add_up_to_the_totals():
    rows = [e(f"2026-{1 + i % 12:02d}-{1 + i % 27:02d}", 7 + i, ["Food", "Rent", "Fun"][i % 3]) for i in range(60)]
    r = year(rows)
    assert sum(x["total"] for x in r["category_matrix"]["rows"]) == r["totals"]["spent"] == sum(c["total"] for c in r["categories"]) == sum(p["total"] for p in r["periods"])


def test_top_shops_are_merged_by_name_ranked_and_capped():
    rows = [e("2026-02-01", 10, shop="ICA"), e("2026-02-02", 30, shop="ica "), e("2026-02-03", 25, shop="Coop"), e("2026-02-04", 99, shop="")]
    r = year(rows)
    assert [(s["shop"], s["total"], s["count"]) for s in r["top_shops"]] == [("ICA", D("40.00"), 2), ("Coop", D("25.00"), 1)]
    assert r["top_shops"][0]["share_pct"] == round(40 / 164 * 100, 1)                    # share of all spending, shopless included
    many = year([e("2026-02-01", 10 + i, shop=f"Shop {i:02d}") for i in range(15)])
    assert len(many["top_shops"]) == 10 and many["top_shops"][0]["shop"] == "Shop 14"


def test_the_largest_expenses_are_listed_biggest_first_and_capped():
    rows = [e("2026-02-01", 10 + i, description=f"item {i}", shop="S", category="Fun") for i in range(15)]
    r = year(rows)
    assert len(r["largest"]) == 10
    assert r["largest"][0] == {"date": "2026-02-01", "category": "Fun", "description": "item 14", "shop": "S", "amount": D("24.00")}
    assert [x["amount"] for x in r["largest"]] == sorted((x["amount"] for x in r["largest"]), reverse=True)


def test_equal_amounts_are_listed_oldest_first():
    r = year([e("2026-05-01", 50, description="later"), e("2026-02-01", 50, description="earlier")])
    assert [x["description"] for x in r["largest"]] == ["earlier", "later"]


def test_refunds_count_so_the_total_matches_the_dashboard():
    r = year([e("2026-02-01", 100, "Food"), e("2026-02-02", -30, "Food")])
    assert r["totals"]["spent"] == D("70.00") and r["categories"][0]["total"] == D("70.00")


def test_rows_with_a_bad_date_are_ignored_and_amounts_may_be_strings_or_ints():
    r = year([{"date": "not a date", "amount": 5, "category": "Food"}, {"date": "2026-02-01", "amount": "12.5", "category": "Food"}, {"date": None, "amount": 1}])
    assert r["totals"]["spent"] == D("12.50") and r["totals"]["count"] == 1


def test_iso_strings_work_as_dates():
    assert year([{"date": "2026-02-01", "amount": 5, "category": "Food"}])["totals"]["spent"] == D("5.00")
