"""Cheapest shop per item: where a shop you use less beats the one you usually buy at."""
import datetime as dt
from decimal import Decimal as D

from app.logic import price_tracker as pt

TODAY = dt.date(2026, 10, 16)


def buy(date, shop, price, item="Milk", unit="Litre", category="Food", brand="", **extra):
    return {"date": dt.date.fromisoformat(date), "description": item, "shop": shop, "price_per_unit": D(str(price)),
            "amount": D(str(price)), "unit": unit, "category": category, "brand": brand, "bill_total_only": False, **extra}


def run(rows, **kw):
    return pt.cheapest_shops(rows, today=TODAY, **kw)


MILK = [
    buy("2026-08-01", "ICA", 15), buy("2026-08-15", "ICA", 14), buy("2026-09-01", "ICA", 16),   # usual: ICA, avg 15
    buy("2026-09-10", "Lidl", 12),                                                              # cheaper: 20% less
]


def test_a_cheaper_shop_than_your_usual_is_found():
    r = run(MILK)
    [m] = r["items"]
    assert m["item"] == "Milk" and m["unit"] == "Litre" and m["shops_compared"] == 2
    assert m["cheapest"]["shop"] == "Lidl" and m["cheapest"]["avg_price"] == D("12.00") and m["cheapest"]["times_bought"] == 1
    assert m["usual"]["shop"] == "ICA" and m["usual"]["avg_price"] == D("15.00") and m["usual"]["times_bought"] == 3
    assert m["saving_per_unit"] == D("3.00") and m["saving_pct"] == 20.0
    assert r["compared"] == 1 and r["already_cheapest"] == 0 and r["total_found"] == 1


def test_nothing_to_say_when_your_usual_shop_is_already_the_cheapest():
    rows = [buy("2026-08-01", "ICA", 10), buy("2026-08-02", "ICA", 11), buy("2026-09-01", "Lidl", 14)]
    r = run(rows)
    assert r["items"] == [] and r["compared"] == 1 and r["already_cheapest"] == 1


def test_an_item_bought_at_one_shop_is_not_compared():
    r = run([buy("2026-08-01", "ICA", 10), buy("2026-09-01", "ICA", 12)])
    assert r == {"months": 12, "compared": 0, "already_cheapest": 0, "items": [], "total_found": 0}


def test_a_small_saving_is_not_worth_a_trip():
    rows = [buy("2026-08-01", "ICA", 10), buy("2026-08-02", "ICA", 10), buy("2026-09-01", "Lidl", 9.8)]
    assert run(rows)["items"] == []                           # 2% under the 5% default
    assert len(run(rows, min_saving_pct=1)["items"]) == 1


def test_the_same_product_is_compared_so_a_cheaper_brand_is_not_a_cheaper_shop():
    rows = [
        buy("2026-08-01", "ICA", 20, brand="Arla"), buy("2026-08-02", "ICA", 20, brand="Arla"),
        buy("2026-09-01", "Lidl", 10, brand="Eldorado"),         # a different brand: not the same product
    ]
    assert run(rows)["compared"] == 0
    rows.append(buy("2026-09-02", "Lidl", 16, brand="Arla"))
    [m] = run(rows)["items"]
    assert m["brand"] == "Arla" and m["cheapest"]["shop"] == "Lidl" and m["saving_pct"] == 20.0


def test_units_and_categories_are_not_mixed():
    rows = [buy("2026-08-01", "ICA", 20, unit="Litre"), buy("2026-08-02", "ICA", 20, unit="Litre"), buy("2026-09-01", "Lidl", 5, unit="Count")]
    assert run(rows)["compared"] == 0
    rows = [buy("2026-08-01", "ICA", 20), buy("2026-08-02", "ICA", 20), buy("2026-09-01", "Lidl", 5, category="Pets")]
    assert run(rows)["compared"] == 0


def test_prices_are_compared_per_base_unit():
    rows = [buy("2026-08-01", "ICA", 20, unit="Kg"), buy("2026-08-02", "ICA", 20, unit="kg"), buy("2026-09-01", "Lidl", 0.015, unit="g")]
    [m] = run(rows)["items"]
    assert m["cheapest"]["shop"] == "Lidl" and m["cheapest"]["avg_price"] == D("15.00") and m["unit"] == "Kg"


def test_only_the_last_months_count_and_zero_means_all_time():
    rows = [buy("2025-01-01", "Lidl", 1), buy("2026-08-01", "ICA", 10), buy("2026-08-02", "ICA", 10)]
    assert run(rows)["compared"] == 0                       # Lidl's price is from 2025: too old for 12 months
    assert run(rows, months=0)["compared"] == 1
    assert run(rows, months=24)["compared"] == 1
    # the window starts on the first of the month, so a purchase on 1 Nov 2025 is still in
    assert run([buy("2025-11-01", "Lidl", 1), buy("2026-08-01", "ICA", 10), buy("2026-08-02", "ICA", 10)])["compared"] == 1


def test_unknown_shops_are_never_recommended_and_bill_totals_are_not_items():
    rows = [buy("2026-08-01", "ICA", 10), buy("2026-08-02", "ICA", 10), buy("2026-09-01", "", 1), buy("2026-09-02", None, 1)]
    assert run(rows)["compared"] == 0
    rows = [buy("2026-08-01", "ICA", 10), buy("2026-08-02", "ICA", 10), buy("2026-09-01", "Lidl", 1, bill_total_only=True)]
    assert run(rows)["compared"] == 0


def test_shop_names_match_ignoring_case_and_spacing():
    rows = [buy("2026-08-01", "ICA", 10), buy("2026-08-02", "ica ", 10), buy("2026-09-01", "Lidl", 5)]
    [m] = run(rows)["items"]
    assert m["usual"]["times_bought"] == 2 and m["shops_compared"] == 2


def test_a_tie_for_your_usual_shop_goes_to_the_one_used_last():
    rows = [buy("2026-08-01", "ICA", 10), buy("2026-08-02", "Coop", 10), buy("2026-09-01", "Lidl", 5), buy("2026-09-05", "Lidl", 5),
            buy("2026-09-09", "Coop", 10), buy("2026-08-20", "ICA", 10)]
    [m] = run(rows)["items"]
    assert m["usual"]["shop"] == "Coop" and m["cheapest"]["shop"] == "Lidl"   # Coop and ICA both 2; Coop was last


def test_biggest_saving_first_and_only_the_top_returned():
    rows = []
    for name, cheap in (("Milk", 12), ("Eggs", 6), ("Bread", 9)):
        rows += [buy("2026-08-01", "ICA", 15, item=name), buy("2026-08-02", "ICA", 15, item=name), buy("2026-09-01", "Lidl", cheap, item=name)]
    r = run(rows)
    assert [i["item"] for i in r["items"]] == ["Eggs", "Bread", "Milk"]            # 60%, 40%, 20%
    top = run(rows, top=2)
    assert [i["item"] for i in top["items"]] == ["Eggs", "Bread"] and top["total_found"] == 3


def test_dates_given_as_text_work_too():
    rows = [{**r, "date": r["date"].isoformat()} for r in MILK]
    assert len(run(rows)["items"]) == 1
