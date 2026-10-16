"""Choosing what goes into one item's price comparison: brand, shops, and unit conversion."""
import datetime as dt
from decimal import Decimal as D

import pytest

from app.logic import price_tracker as pt

DETAIL = "/api/analytics/price-trends/detail"


def buy(client, h, item, price, *, date, qty=1, unit="Count", shop="ICA", brand="", category="Food"):
    r = client.post(
        "/api/expenses",
        json={"date": date, "category": category, "description": item, "amount": str(price), "quantity": qty,
              "unit": unit, "shop": shop, "brand": brand, "currency": "SEK"},
        headers=h,
    )
    assert r.status_code == 201, r.text


def detail(client, h, item="Milk", **params):
    r = client.get(DETAIL, params={"item": item, **params}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def milk(client, make_user):
    """Four purchases of Milk across two brands and three shops (one with no brand, one with no shop)."""
    _, h = make_user()
    buy(client, h, "Milk", 10, date="2026-01-01", brand="Arla", shop="ICA")
    buy(client, h, "Milk", 12, date="2026-02-01", brand="arla", shop="ICA Maxi")
    buy(client, h, "Milk", 8, date="2026-03-01", brand="Local", shop="Lidl")
    buy(client, h, "Milk", 9, date="2026-04-01", brand="", shop="")
    return client, h


# --- item names stay separate ----------------------------------------------------------

def test_milk_and_arla_milk_are_separate_items_while_case_variants_are_one(client, make_user):
    _, h = make_user()
    for i, (name, price) in enumerate([("Milk", 10), ("milk", 11), ("MILK", 12), ("Arla Milk", 14), ("Arla milk", 15)], 1):
        buy(client, h, name, price, date=f"2026-0{i}-01")

    rows = client.get("/api/analytics/price-trends", headers=h).json()

    assert {r["item"].lower(): r["purchases"] for r in rows} == {"milk": 3, "arla milk": 2}


# --- unit conversion, as in "rice 500 g and 5 kg" -------------------------------------

@pytest.mark.parametrize("small_unit", ["g", "gm", "grm", "Gram", "GRAMS"])
def test_rice_bought_in_grams_and_in_kilos_is_compared_per_kilo(client, make_user, small_unit):
    _, h = make_user()
    buy(client, h, "Rice", 30, qty=500, unit=small_unit, date="2026-01-01")   # 0.06 per g = 60 per kg
    buy(client, h, "Rice", 250, qty=5, unit="kg", date="2026-02-01")           # 50 per kg

    [row] = client.get("/api/analytics/price-trends", headers=h).json()
    d = detail(client, h, "Rice", unit="Kg")

    assert (row["unit"], row["purchases"]) == ("Kg", 2)
    assert (float(row["first_price"]), float(row["last_price"])) == (60.0, 50.0)
    assert [float(p["price"]) for p in d["history"]] == [60.0, 50.0]
    assert d["summary"]["trend"] == "Decreasing"
    assert float(d["summary"]["avg_price"]) == 55.0


# --- the detail view: defaults and options ---------------------------------------------

def test_by_default_everything_is_included_and_the_choices_are_listed(milk):
    client, h = milk

    d = detail(client, h)

    assert d["summary"]["purchases"] == 4
    assert [p["price"] for p in d["history"]] == [10.0, 12.0, 8.0, 9.0]
    assert {s["shop"] for s in d["shops"]} == {"ICA", "ICA Maxi", "Lidl", "Unknown"}
    brands = {b["name"].lower(): b["count"] for b in d["options"]["brands"]}
    assert brands == {"arla": 2, "local": 1, "": 1}
    assert {s["name"] for s in d["options"]["shops"]} == {"ICA", "ICA Maxi", "Lidl", "Unknown"}


def test_ica_ica_maxi_and_ica_nara_stay_separate_shops(client, make_user):
    _, h = make_user()
    for shop, date in (("ICA", "01"), ("ICA Maxi", "02"), ("Ica Nara", "03"), ("ica", "04")):
        buy(client, h, "Rice", 20, date=f"2026-01-{date}", shop=shop)

    d = detail(client, h, "Rice")

    assert {s["shop"]: s["times_bought"] for s in d["shops"]} == {"ICA": 2, "ICA Maxi": 1, "Ica Nara": 1}


# --- narrowing by brand -----------------------------------------------------------------

def test_choosing_a_brand_narrows_everything_but_keeps_all_the_choices(milk):
    client, h = milk

    d = detail(client, h, brand="ARLA")  # case does not matter

    assert d["summary"]["purchases"] == 2
    assert [p["price"] for p in d["history"]] == [10.0, 12.0]
    assert {s["shop"] for s in d["shops"]} == {"ICA", "ICA Maxi"}
    assert len(d["options"]["brands"]) == 3 and len(d["options"]["shops"]) == 4  # unchanged by the choice


def test_an_empty_brand_means_purchases_with_no_brand(milk):
    client, h = milk

    d = detail(client, h, brand="")

    assert [p["price"] for p in d["history"]] == [9.0]
    assert d["summary"]["purchases"] == 1


def test_an_unknown_brand_gives_an_empty_comparison_not_an_error(milk):
    client, h = milk

    d = detail(client, h, brand="Nobody")

    assert d["summary"] is None and d["shops"] == [] and d["history"] == []
    assert len(d["options"]["brands"]) == 3


# --- choosing shops ---------------------------------------------------------------------

def test_only_the_chosen_shops_are_included(milk):
    client, h = milk

    d = detail(client, h, shop=["ICA", "Lidl"])

    assert {s["shop"] for s in d["shops"]} == {"ICA", "Lidl"}
    assert [p["price"] for p in d["history"]] == [10.0, 8.0]
    assert d["summary"]["purchases"] == 2
    assert float(d["summary"]["avg_price"]) == 9.0


def test_shop_names_are_matched_ignoring_case_and_unknown_is_a_choice(milk):
    client, h = milk

    d = detail(client, h, shop=["ica", "unknown"])

    assert {s["shop"] for s in d["shops"]} == {"ICA", "Unknown"}


def test_brand_and_shops_combine(milk):
    client, h = milk

    d = detail(client, h, brand="Arla", shop=["ICA Maxi"])

    assert [p["price"] for p in d["history"]] == [12.0]


def test_the_old_shop_and_history_endpoints_accept_the_same_choices(milk):
    client, h = milk
    base = "/api/analytics/price-trends"

    shops = client.get(f"{base}/shops", params={"item": "Milk", "brand": "Arla", "shop": ["ICA"]}, headers=h).json()
    history = client.get(f"{base}/history", params={"item": "Milk", "shop": ["Lidl", "Unknown"]}, headers=h).json()

    assert [s["shop"] for s in shops] == ["ICA"]
    assert [p["price"] for p in history] == [8.0, 9.0]


def test_the_detail_is_private_and_needs_a_login(client, make_user):
    _, alice = make_user()
    _, bob = make_user()
    buy(client, alice, "Milk", 10, date="2026-01-01")
    buy(client, alice, "Milk", 12, date="2026-02-01")

    assert detail(client, bob)["summary"] is None
    assert client.get(DETAIL, params={"item": "Milk"}).status_code == 401


# --- the trend label --------------------------------------------------------------------

def row(day, price):
    return {"description": "Flour", "unit": "Kg", "category": "Food", "date": dt.date(2026, 1, day),
            "amount": D(price), "price_per_unit": D(price), "shop": "x", "brand": ""}


@pytest.mark.parametrize(
    "prices, expected",
    [
        ([20, 24], "Increasing"),          # used to say "Stable": both averages were the same two prices
        ([24, 20], "Decreasing"),
        ([20, 20], "Stable"),
        ([20, 24, 30], "Increasing"),      # likewise
        ([30, 24, 20], "Decreasing"),
        ([20, 30, 20], "Stable"),          # ends where it started
        ([10, 12, 20, 30], "Increasing"),
        ([10, 20, 12, 8, 6], "Decreasing"),
        ([10, 11, 12, 13, 14, 15, 16], "Increasing"),   # 7 purchases: first 3 against last 3, as before
        ([16, 15, 14, 13, 12, 11, 10], "Decreasing"),
    ],
)
def test_trend_label(prices, expected):
    [t] = pt.price_trends([row(i + 1, p) for i, p in enumerate(prices)])
    assert t["trend"] == expected


def test_a_single_purchase_has_a_summary_but_no_trend():
    s = pt.price_summary([row(1, 20)])
    assert (s["purchases"], s["trend"], s["change"], s["volatility"]) == (1, "Stable", 0, 0.0)
    assert pt.price_summary([]) is None
