"""Price rises: the same product at the same shop costing more than you usually paid."""
import datetime as dt
from decimal import Decimal as D

from app.logic import alerts as al
from app.logic import price_tracker as pt

TODAY = dt.date(2026, 10, 16)


def buy(date, price, shop="ICA", item="Milk", unit="Litre", category="Food", brand="", **extra):
    return {"date": dt.date.fromisoformat(date), "description": item, "shop": shop, "price_per_unit": D(str(price)),
            "amount": D(str(price)), "unit": unit, "category": category, "brand": brand, "bill_total_only": False, **extra}


def run(rows, **kw):
    return pt.price_rises(rows, today=TODAY, **kw)


MILK = [buy("2026-07-01", 10), buy("2026-08-01", 10), buy("2026-09-01", 10), buy("2026-10-10", 13)]   # 30% up


def test_a_rise_is_found_and_described():
    r = run(MILK)
    [m] = r["items"]
    assert (m["item"], m["shop"], m["unit"], m["category"]) == ("Milk", "ICA", "Litre", "Food")
    assert m["latest_price"] == D("13.00") and m["usual_price"] == D("10.00") and m["rise_per_unit"] == D("3.00")
    assert m["rise_pct"] == 30.0 and m["latest_date"] == "2026-10-10" and m["earlier_purchases"] == 3
    assert r["total_found"] == 1 and r["checked"] == 1


def test_the_usual_price_is_the_average_of_the_earlier_purchases():
    rows = [buy("2026-07-01", 8), buy("2026-08-01", 12), buy("2026-10-10", 13)]    # usual 10
    assert run(rows)["items"][0]["usual_price"] == D("10.00")


def test_a_small_rise_is_not_reported_but_is_checked():
    rows = [buy("2026-07-01", 10), buy("2026-08-01", 10), buy("2026-10-10", 10.5)]   # 5%
    r = run(rows)
    assert r["items"] == [] and r["checked"] == 1
    assert len(run(rows, min_rise_pct=5)["items"]) == 1


def test_a_fall_or_no_change_is_not_a_rise():
    assert run([buy("2026-07-01", 10), buy("2026-08-01", 10), buy("2026-10-10", 8)])["items"] == []
    assert run([buy("2026-07-01", 10), buy("2026-08-01", 10), buy("2026-10-10", 10)])["items"] == []


def test_one_earlier_purchase_is_not_a_usual_price():
    rows = [buy("2026-08-01", 10), buy("2026-10-10", 20)]
    r = run(rows)
    assert r["items"] == [] and r["checked"] == 0
    assert len(run(rows, min_earlier=1)["items"]) == 1


def test_only_a_recent_purchase_counts_as_news():
    rows = [buy("2026-06-01", 10), buy("2026-07-01", 10), buy("2026-08-01", 20)]    # the rise was in August
    assert run(rows)["items"] == []
    assert len(run(rows, recent_days=90)["items"]) == 1


def test_the_same_shop_is_followed_so_changing_shop_is_not_a_rise():
    rows = [buy("2026-07-01", 10), buy("2026-08-01", 10), buy("2026-10-10", 20, shop="Coop")]
    assert run(rows)["checked"] == 0


def test_the_same_brand_is_followed():
    rows = [buy("2026-07-01", 10, brand="Arla"), buy("2026-08-01", 10, brand="Arla"), buy("2026-10-10", 20, brand="Eldorado")]
    assert run(rows)["checked"] == 0


def test_units_and_categories_are_not_mixed():
    rows = [buy("2026-07-01", 10), buy("2026-08-01", 10), buy("2026-10-10", 20, unit="Count")]
    assert run(rows)["checked"] == 0
    rows = [buy("2026-07-01", 10), buy("2026-08-01", 10), buy("2026-10-10", 20, category="Pets")]
    assert run(rows)["checked"] == 0


def test_prices_in_different_units_of_one_kind_are_compared_per_base_unit():
    rows = [buy("2026-07-01", 10, unit="Kg"), buy("2026-08-01", 10, unit="kg"), buy("2026-10-10", 0.013, unit="g")]
    [m] = run(rows)["items"]
    assert m["unit"] == "Kg" and m["latest_price"] == D("13.00") and m["rise_pct"] == 30.0


def test_the_baseline_leaves_out_prices_from_too_long_ago():
    rows = [buy("2024-01-01", 1), buy("2024-02-01", 1), buy("2026-08-01", 10), buy("2026-09-01", 10), buy("2026-10-10", 12)]
    [m] = run(rows)["items"]
    assert m["usual_price"] == D("10.00") and m["earlier_purchases"] == 2
    assert run(rows, baseline_months=0)["items"][0]["earlier_purchases"] == 4      # 0 = all history


def test_bill_totals_future_dates_and_blank_items_are_ignored():
    rows = MILK[:3] + [buy("2026-10-10", 99, bill_total_only=True)]
    assert run(rows)["checked"] == 0
    rows = MILK[:3] + [buy("2026-11-20", 99)]
    assert run(rows)["checked"] == 0
    rows = [buy("2026-07-01", 10, item=" "), buy("2026-08-01", 10, item=""), buy("2026-10-10", 20, item=None)]
    assert run(rows)["checked"] == 0


def test_names_match_ignoring_case_and_spacing():
    rows = [buy("2026-07-01", 10, shop="ICA"), buy("2026-08-01", 10, shop="ica "), buy("2026-10-10", 20, shop="Ica", item="milk")]
    assert len(run(rows)["items"]) == 1


def test_the_biggest_rise_comes_first_and_only_the_top_are_returned():
    rows = []
    for name, now in (("Milk", 12), ("Eggs", 20), ("Bread", 15)):
        rows += [buy("2026-07-01", 10, item=name), buy("2026-08-01", 10, item=name), buy("2026-10-10", now, item=name)]
    assert [i["item"] for i in run(rows)["items"]] == ["Eggs", "Bread", "Milk"]
    top = run(rows, top=2)
    assert [i["item"] for i in top["items"]] == ["Eggs", "Bread"] and top["total_found"] == 3


def test_a_free_item_cannot_have_risen():
    rows = [buy("2026-07-01", 0), buy("2026-08-01", 0), buy("2026-10-10", 5)]
    assert run(rows)["items"] == []


def test_purchases_on_one_day_are_ordered_by_id():
    rows = [buy("2026-07-01", 10, id=1), buy("2026-08-01", 10, id=2), buy("2026-10-10", 20, id=4), buy("2026-10-10", 10, id=3)]
    assert run(rows)["items"][0]["latest_price"] == D("20.00")


def test_dates_given_as_text_work():
    assert len(run([{**r, "date": r["date"].isoformat()} for r in MILK])["items"]) == 1


# --- the bell ---------------------------------------------------------------------------------

def rise(item, pct, shop="ICA", brand=""):
    return {"item": item, "brand": brand, "shop": shop, "unit": "Litre", "category": "Food", "latest_price": D("13.00"),
            "usual_price": D("10.00"), "rise_pct": pct}


def test_each_big_rise_gets_a_bell_alert_with_a_severity_by_size():
    out = al.price_rise_alerts({"items": [rise("Eggs", 40.0), rise("Milk", 12.0, brand="Arla")], "total_found": 2})
    assert [(a["severity"], a["category"]) for a in out] == [("warning", "Prices"), ("caution", "Prices")]
    assert out[0]["message"] == "Eggs at ICA now costs 13.00 per Litre, 40% more than your usual 10.00"
    assert "Milk (Arla) at ICA" in out[1]["message"]
    assert len({a["id"] for a in out}) == 2 and out[0]["id"] == "price:eggs||ica|litre|food"


def test_a_threshold_rise_is_a_warning():
    assert al.price_rise_alerts({"items": [rise("A", 25.0)], "total_found": 1})[0]["severity"] == "warning"
    assert al.price_rise_alerts({"items": [rise("A", 24.9)], "total_found": 1})[0]["severity"] == "caution"


def test_the_rest_are_rolled_into_one_line_so_budget_alerts_are_not_buried():
    items = [rise(f"Item{i}", 50 - i) for i in range(3)]
    out = al.price_rise_alerts({"items": items, "total_found": 7})
    assert len(out) == 4 and out[-1]["id"] == "price:more" and out[-1]["severity"] == "info"
    assert out[-1]["message"] == "4 more items have gone up in price. See Insights, Prices."
    one = al.price_rise_alerts({"items": items, "total_found": 4})
    assert one[-1]["message"].startswith("1 more item has gone")


def test_no_rises_no_alerts():
    assert al.price_rise_alerts({"items": [], "total_found": 0}) == []
    assert al.price_rise_alerts({}) == []


# --- the window used before renaming -----------------------------------------------------------

def test_only_purchases_that_can_matter_go_on_to_renaming():
    rows = [buy("2024-01-01", 1), buy("2025-09-30", 2), buy("2025-10-01", 3), buy("2026-10-10", 4), buy("2026-11-20", 5),
            buy("2026-10-10", 6, bill_total_only=True), {**buy("2026-10-10", 7), "date": "not a date"}]
    kept = pt.rows_for_price_rises(rows, today=TODAY)
    assert [r["price_per_unit"] for r in kept] == [D("3"), D("4")]       # 12 months back starts on 1 Oct 2025
    assert len(pt.rows_for_price_rises(rows, today=TODAY, baseline_months=0)) == 4   # all history, but no totals, future or bad dates


def test_leaving_old_rows_out_never_changes_the_answer():
    rows = [buy("2023-01-01", 1), buy("2024-06-01", 1), buy("2026-07-01", 10), buy("2026-08-01", 10), buy("2026-10-10", 13)]
    assert run(rows) == run(pt.rows_for_price_rises(rows, today=TODAY))
