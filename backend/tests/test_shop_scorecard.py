"""Shop scorecard: spend, visits and the price index (is a shop dearer or cheaper for the same things?)."""
import datetime as dt
from decimal import Decimal as D

import pytest

from app.logic import shop_scorecard as sc

TODAY = dt.date(2026, 10, 16)


def e(shop, item, price, date="2026-09-01", qty=1, unit="Count", brand="", category="Food", **extra):
    """An expense bought for `price` per unit (so it cost price * qty)."""
    return {
        "date": dt.date.fromisoformat(date), "shop": shop, "description": item, "category": category, "brand": brand,
        "unit": unit, "quantity": qty, "price_per_unit": D(str(price)), "amount": D(str(price)) * D(str(qty)), **extra,
    }


def card(rows, **kw):
    return sc.shop_scorecard(rows, today=TODAY, **kw)


def shop(result, name):
    return next(s for s in result["shops"] if s["shop"] == name)


def shared(pairs, shops=("ICA", "Lidl"), **kw):
    """Items bought once at each of two shops, at the given (price at first, price at second)."""
    return [e(s, item, price, **kw) for item, prices in pairs.items() for s, price in zip(shops, prices)]


# --- the price index -------------------------------------------------------------------

def test_a_shop_that_is_dearer_on_everything_shared_scores_above_100_and_the_other_below():
    r = card(shared({"Rice": (10, 12), "Milk": (20, 24), "Bread": (30, 36)}))

    ica, lidl = shop(r, "ICA"), shop(r, "Lidl")
    assert (ica["price_index"], lidl["price_index"]) == (90.9, 109.1)  # around the 11 / 22 / 33 reference prices
    assert (ica["items_compared"], ica["cheapest_on"]) == (3, 3)
    assert (lidl["items_compared"], lidl["cheapest_on"]) == (3, 0)
    assert lidl["potential_saving"] == D("12.00") and ica["potential_saving"] == D("0.00")
    assert ica["coverage_pct"] == 100.0


def test_what_you_spend_on_each_item_weights_the_index():
    # ICA is half Lidl's price on A, equal on B, double on C. Counted equally that is exactly 100;
    # ICA's money is mostly in the items where it is dear (C, B) so it scores above 100.
    rows = [e("ICA", "A", 10), e("Lidl", "A", 20), e("ICA", "B", 30), e("Lidl", "B", 30), e("ICA", "C", 20), e("Lidl", "C", 10)]

    r = card(rows)

    assert shop(r, "ICA")["price_index"] == 105.6
    assert shop(r, "Lidl")["price_index"] == 105.6


def test_all_shops_charging_the_same_is_an_index_of_100_with_nothing_to_save():
    r = card(shared({"Rice": (10, 10), "Milk": (20, 20), "Bread": (30, 30)}))

    assert [s["price_index"] for s in r["shops"]] == [100.0, 100.0]
    assert [s["cheapest_on"] for s in r["shops"]] == [0, 0]  # nobody is cheaper than anybody
    assert r["opportunities"] == []


def test_the_index_needs_enough_shared_items_but_the_comparison_still_counts():
    r = card(shared({"Rice": (10, 12), "Milk": (20, 24)}))

    assert shop(r, "ICA")["price_index"] is None
    assert shop(r, "ICA")["items_compared"] == 2 and shop(r, "ICA")["cheapest_on"] == 2
    assert r["min_items_for_index"] == 3


def test_items_bought_at_only_one_shop_are_not_compared():
    rows = shared({"Rice": (10, 12), "Milk": (20, 24), "Bread": (30, 36)}) + [e("ICA", "Caviar", 500)]

    ica = shop(card(rows), "ICA")

    assert ica["items_compared"] == 3
    assert ica["coverage_pct"] == round(60 / 560 * 100, 1)  # only part of ICA's spend rests on the index


def test_three_shops_and_a_tie_for_cheapest():
    rows = []
    for item, prices in {"Rice": (10, 10, 16), "Milk": (20, 20, 32), "Bread": (30, 30, 48)}.items():
        rows += [e(s, item, p) for s, p in zip(("ICA", "Coop", "Lidl"), prices)]

    r = card(rows)

    assert shop(r, "ICA")["cheapest_on"] == 3 and shop(r, "Coop")["cheapest_on"] == 3 and shop(r, "Lidl")["cheapest_on"] == 0
    assert {o["cheaper_shop"] for o in r["opportunities"]} == {"Coop"}  # a tie goes to the alphabetically first


# --- comparing like with like -----------------------------------------------------------

def test_a_different_brand_is_a_different_item():
    rows = [e("ICA", "Milk", 20, brand="Arla"), e("Lidl", "Milk", 14, brand="Local")] + shared({"Rice": (10, 12), "Bread": (30, 36)})

    r = card(rows)

    assert shop(r, "ICA")["items_compared"] == 2  # Arla vs Local milk is not a price difference


def test_the_same_brand_in_any_case_is_compared():
    rows = [e("ICA", "Milk", 20, brand="Arla"), e("Lidl", "milk", 24, brand="ARLA")]

    assert shop(card(rows), "Lidl")["items_compared"] == 1


def test_a_different_category_or_kind_of_unit_is_a_different_item():
    rows = [e("ICA", "Soap", 20, category="Home"), e("Lidl", "Soap", 5, category="Personal"),
            e("ICA", "Oil", 40, unit="Litre"), e("Lidl", "Oil", 5, unit="Kg")]

    assert [s["items_compared"] for s in card(rows)["shops"]] == [0, 0]


def test_grams_and_kilos_are_compared_per_kilo():
    rows = [e("ICA", "Rice", "0.06", qty=500, unit="g"), e("Lidl", "Rice", 50, qty=5, unit="kg")]  # 60 per kg vs 50 per kg

    r = card(rows)

    [opp] = r["opportunities"]
    assert (opp["shop"], opp["cheaper_shop"], opp["unit"]) == ("ICA", "Lidl", "Kg")
    assert (opp["price"], opp["cheaper_price"], opp["pay_more_pct"]) == (D("60.00"), D("50.00"), 20.0)
    assert opp["saving"] == D("5.00")  # 10 more per kg, and 0.5 kg was bought at ICA


# --- awkward rows -------------------------------------------------------------------------

def test_a_bills_total_counts_as_spend_and_a_visit_but_is_never_an_item_price():
    rows = [e("ICA", "Groceries", 300, bill_total_only=True), e("Lidl", "Groceries", 50)]

    r = card(rows)

    ica = shop(r, "ICA")
    assert (ica["spend"], ica["visits"]) == (D("300.00"), 1)
    assert ica["items_compared"] == 0 and r["opportunities"] == []


def test_a_recorded_bill_total_stores_its_shop_in_the_description_and_still_counts_for_that_shop():
    # How the app saves a bill recorded as a total: shop empty, shop name in the description.
    rows = [e("", "ICA Maxi", 300, bill_total_only=True), e("ICA Maxi", "Rice", 12), e("", "  ", 50, bill_total_only=True),
            e("", "Rent", 9000)]  # an ordinary expense with no shop stays "no shop"

    r = card(rows)

    maxi = shop(r, "ICA Maxi")
    assert (maxi["spend"], maxi["purchases"], maxi["visits"]) == (D("312.00"), 2, 1)
    assert r["unknown"] == {"spend": D("9050.00"), "purchases": 2}
    assert maxi["items_compared"] == 0


def test_with_bill_shops_leaves_everything_else_alone_and_does_not_mutate():
    rows = [e("", "ICA", 10, bill_total_only=True), e("Lidl", "Lidl", 10, bill_total_only=True), e("", "Tea", 5)]

    out = sc.with_bill_shops(rows)

    assert [r["shop"] for r in out] == ["ICA", "Lidl", ""]
    assert rows[0]["shop"] == ""


def test_purchases_with_no_shop_are_kept_apart_and_never_compared():
    rows = [e("", "Rent", 9000), e("  ", "Rice", 10), e(None, "Milk", 20), e("ICA", "Rice", 12), e("Lidl", "Rice", 11)]

    r = card(rows)

    assert r["unknown"] == {"spend": D("9030.00"), "purchases": 3}
    assert r["named_spend"] == D("23.00")
    assert sum(s["share_pct"] for s in r["shops"]) == pytest.approx(100, abs=0.2)  # shares are of named shops only
    assert all(s["shop"] != sc.UNKNOWN_SHOP for s in r["shops"])


def test_free_and_unpriced_items_are_ignored_in_comparisons_but_still_counted_as_purchases():
    rows = [e("ICA", "Sample", 0), e("Lidl", "Sample", 5)]

    r = card(rows)

    assert shop(r, "ICA")["purchases"] == 1 and shop(r, "ICA")["items_compared"] == 0


def test_shops_that_differ_only_in_case_or_spacing_are_one_shop_but_ica_and_ica_maxi_are_two():
    rows = [e("ICA", "A", 1, date="2026-09-01"), e("ica", "A", 1, date="2026-09-02"), e(" Ica ", "A", 1, date="2026-09-03"),
            e("ICA Maxi", "A", 1), e("Ica Nara", "A", 1)]

    r = card(rows)

    assert sorted(s["shop"] for s in r["shops"]) == ["ICA", "ICA Maxi", "Ica Nara"]
    assert shop(r, "ICA")["purchases"] == 3 and shop(r, "ICA")["visits"] == 3


def test_items_match_ignoring_case_and_spacing():
    rows = [e("ICA", "Rice", 10), e("Lidl", " rice ", 12)]

    assert shop(card(rows), "ICA")["items_compared"] == 1


# --- spend and visits ----------------------------------------------------------------------

def test_visits_are_distinct_days_at_a_shop_not_purchases():
    rows = [e("ICA", "A", 10, date="2026-09-01"), e("ICA", "B", 20, date="2026-09-01"), e("ICA", "C", 30, date="2026-09-01"),
            e("ICA", "A", 40, date="2026-09-20"), e("Lidl", "A", 5, date="2026-09-01")]

    r = card(rows)
    ica = shop(r, "ICA")

    assert (ica["purchases"], ica["visits"]) == (4, 2)
    assert (ica["spend"], ica["avg_visit"]) == (D("100.00"), D("50.00"))
    assert (ica["first_visit"], ica["last_visit"]) == ("2026-09-01", "2026-09-20")
    assert [s["shop"] for s in r["shops"]] == ["ICA", "Lidl"]  # biggest spend first
    assert ica["share_pct"] == round(100 / 105 * 100, 1)


def test_visits_per_month_uses_the_time_you_have_data_for_not_the_whole_window():
    # Six-month window, but the first expense is only ~61 days old: 2 months, not 6.
    rows = [e("ICA", "A", 10, date="2026-08-16"), e("ICA", "A", 10, date="2026-09-16"), e("ICA", "A", 10, date="2026-10-01"),
            e("ICA", "A", 10, date="2026-10-10")]

    assert shop(card(rows), "ICA")["visits_per_month"] == round(4 / (61 / 30.4375), 1)


def test_visits_per_month_never_divides_by_less_than_one_month():
    rows = [e("ICA", "A", 10, date="2026-10-15"), e("ICA", "A", 10, date="2026-10-16")]

    assert shop(card(rows), "ICA")["visits_per_month"] == 2.0


# --- the period ---------------------------------------------------------------------------

def test_the_window_covers_the_last_n_months_and_all_time_is_zero():
    rows = [e("ICA", "A", 1, date="2026-10-10"), e("ICA", "A", 1, date="2026-07-16"), e("ICA", "A", 1, date="2026-07-15"),
            e("ICA", "A", 1, date="2025-01-01")]

    assert shop(card(rows, months=1), "ICA")["purchases"] == 1
    assert shop(card(rows, months=3), "ICA")["purchases"] == 2     # back to 2026-07-16, inclusive
    assert shop(card(rows, months=12), "ICA")["purchases"] == 3
    assert shop(card(rows, months=0), "ICA")["purchases"] == 4
    assert card(rows, months=3)["period"] == {"months": 3, "from": "2026-07-16", "to": "2026-10-16"}


def test_future_dated_spending_is_left_out():
    rows = [e("ICA", "A", 10, date="2026-10-16"), e("ICA", "A", 999, date="2026-10-17")]

    assert shop(card(rows), "ICA")["spend"] == D("10.00")


def test_nothing_in_the_window_is_unavailable_not_an_error():
    r = card([e("ICA", "A", 10, date="2020-01-01")], months=1)

    assert r["available"] is False and r["shops"] == [] and r["opportunities"] == []
    assert card([])["available"] is False
    assert card([])["period"]["from"] == "2026-04-16"            # the window is defined even when empty
    assert card([], months=0)["period"]["from"] is None          # all time with no data has no start


# --- where to save -------------------------------------------------------------------------

def test_the_biggest_savings_come_first_and_only_a_handful_are_listed():
    rows = []
    for i in range(8):
        rows += [e("ICA", f"Item{i}", 10 + i), e("Lidl", f"Item{i}", 10 + i + (i + 1) * 5)]

    r = card(rows)

    assert len(r["opportunities"]) == sc.MAX_OPPORTUNITIES
    savings = [o["saving"] for o in r["opportunities"]]
    assert savings == sorted(savings, reverse=True) and savings[0] == D("40.00")
    assert all(o["shop"] == "Lidl" and o["cheaper_shop"] == "ICA" for o in r["opportunities"])


def test_the_saving_is_scaled_by_how_much_you_bought():
    rows = [e("ICA", "Rice", 10, qty=3), e("Lidl", "Rice", 8, qty=1)]  # 2 less per unit, 3 units bought at ICA

    [opp] = card(rows)["opportunities"]

    assert (opp["shop"], opp["saving"]) == ("ICA", D("6.00"))


def test_every_shop_row_has_the_documented_fields():
    r = card(shared({"Rice": (10, 12), "Milk": (20, 24), "Bread": (30, 36)}))

    assert set(r["shops"][0]) == {
        "shop", "spend", "share_pct", "purchases", "visits", "visits_per_month", "avg_visit", "first_visit", "last_visit",
        "price_index", "items_compared", "cheapest_on", "coverage_pct", "potential_saving",
    }
    assert set(r) == {"period", "available", "named_spend", "unknown", "shops", "opportunities", "min_items_for_index"}
