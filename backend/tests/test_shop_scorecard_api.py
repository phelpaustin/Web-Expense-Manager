import datetime as dt
from decimal import Decimal

import pytest

URL = "/api/analytics/shops"


def day(n):
    """A date n days ago."""
    return (dt.date.today() - dt.timedelta(days=n)).isoformat()


def buy(client, h, shop, item, price, *, qty=1, unit="Count", when=None, brand="", category="Food", **extra):
    r = client.post(
        "/api/expenses",
        json={"date": when or day(5), "category": category, "description": item, "amount": str(Decimal(str(price)) * qty), "quantity": qty,
              "unit": unit, "shop": shop, "brand": brand, "currency": "SEK", **extra},
        headers=h,
    )
    assert r.status_code == 201, r.text


def card(client, h, **params):
    r = client.get(URL, params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def shop(result, name):
    return next(s for s in result["shops"] if s["shop"] == name)


@pytest.fixture
def user(client, make_user):
    _, h = make_user()
    for item, (a, b) in {"Rice": (10, 12), "Milk": (20, 24), "Bread": (30, 36)}.items():
        buy(client, h, "ICA", item, a, when=day(10))
        buy(client, h, "Lidl", item, b, when=day(3))
    return client, h


def test_the_scorecard_for_two_shops(user):
    client, h = user

    r = card(client, h)

    assert r["available"] is True and r["currency"] == "SEK" and r["unconverted_count"] == 0
    ica, lidl = shop(r, "ICA"), shop(r, "Lidl")
    assert [s["shop"] for s in r["shops"]] == ["Lidl", "ICA"]  # Lidl spent more (72 vs 60)
    assert (ica["price_index"], lidl["price_index"]) == (90.9, 109.1)
    assert (ica["visits"], lidl["visits"]) == (1, 1)  # all three items were bought on one trip to each
    assert float(lidl["potential_saving"]) == 12.0
    assert [(o["item"], o["shop"], o["cheaper_shop"]) for o in r["opportunities"]][0] == ("Bread", "Lidl", "ICA")
    assert r["named_spend"] == 132 and r["min_items_for_index"] == 3


def test_the_period_is_chosen_with_months_and_zero_means_all_time(client, make_user):
    _, h = make_user()
    buy(client, h, "ICA", "A", 10, when=day(10))
    buy(client, h, "ICA", "A", 10, when=day(100))
    buy(client, h, "ICA", "A", 10, when=day(400))

    counts = {m: shop(card(client, h, months=m), "ICA")["purchases"] for m in (1, 6, 24, 0)}

    assert counts == {1: 1, 6: 2, 24: 3, 0: 3}
    assert card(client, h)["period"]["months"] == 6  # the default


@pytest.mark.parametrize("bad", [-1, 61, "x", ""])
def test_months_must_be_between_0_and_60(user, bad):
    client, h = user
    assert client.get(URL, params={"months": bad}, headers=h).status_code == 422


def test_it_needs_a_login_and_shows_only_your_own_shops(user, make_user):
    client, h = user
    _, other = make_user()

    assert client.get(URL).status_code == 401
    assert card(client, other) ["available"] is False
    assert card(client, other)["shops"] == []
    assert card(client, h)["available"] is True


def test_prices_in_grams_and_kilos_compare_per_kilo(client, make_user):
    _, h = make_user()
    buy(client, h, "ICA", "Rice", "0.06", qty=500, unit="g")
    buy(client, h, "Lidl", "Rice", 50, qty=5, unit="kg")

    [opp] = card(client, h)["opportunities"]

    assert (opp["shop"], opp["unit"], float(opp["price"]), float(opp["cheaper_price"])) == ("ICA", "Kg", 60.0, 50.0)


def test_case_variants_are_one_shop_and_one_item(client, make_user):
    _, h = make_user()
    buy(client, h, "ICA", "Rice", 10, when=day(5))
    buy(client, h, "ica", "rice", 10, when=day(6))
    buy(client, h, "Lidl", "RICE", 12, when=day(7))

    r = card(client, h)

    assert sorted(s["shop"] for s in r["shops"]) == ["ICA", "Lidl"]
    assert shop(r, "ICA")["purchases"] == 2
    assert shop(r, "ICA")["items_compared"] == 1


def test_saved_shop_merges_apply_and_separate_shops_stay_separate(client, make_user):
    _, h = make_user()
    buy(client, h, "ICA", "A", 10)
    buy(client, h, "ICA Maxi", "A", 10)
    buy(client, h, "Ica Nara", "A", 10)
    assert sorted(s["shop"] for s in card(client, h)["shops"]) == ["ICA", "ICA Maxi", "Ica Nara"]

    client.post("/api/aliases/merge", json={"kind": "shop", "names": ["ICA Maxi"], "canonical": "ICA"}, headers=h)

    r = card(client, h)
    assert sorted(s["shop"] for s in r["shops"]) == ["ICA", "Ica Nara"]
    assert shop(r, "ICA")["purchases"] == 2


def test_a_recorded_bill_total_counts_as_spend_but_not_as_an_item_price(client, make_user):
    _, h = make_user()
    client.post("/api/pending-bills", json={"date": day(4), "shop": "ICA", "amount": "300"}, headers=h)  # recorded as a total
    buy(client, h, "Lidl", "Groceries", 50)

    r = card(client, h)

    assert float(shop(r, "ICA")["spend"]) == 300.0
    assert shop(r, "ICA")["items_compared"] == 0 and r["opportunities"] == []


def test_a_bill_total_is_credited_to_the_shop_named_on_the_bill_and_follows_shop_merges(client, make_user):
    _, h = make_user()
    client.post("/api/pending-bills", json={"date": day(4), "shop": "ICA Maxi", "amount": "300"}, headers=h)
    client.post("/api/pending-bills", json={"date": day(8), "shop": "ICA", "amount": "100"}, headers=h)

    r = card(client, h)
    assert r["unknown"]["purchases"] == 0  # not "no shop": the bill says where it was
    assert (float(shop(r, "ICA Maxi")["spend"]), float(shop(r, "ICA")["spend"])) == (300.0, 100.0)

    client.post("/api/aliases/merge", json={"kind": "shop", "names": ["ICA Maxi"], "canonical": "ICA"}, headers=h)

    merged = card(client, h)
    assert [(s["shop"], float(s["spend"]), s["visits"]) for s in merged["shops"]] == [("ICA", 400.0, 2)]


def test_spending_with_no_shop_is_reported_apart(client, make_user):
    _, h = make_user()
    buy(client, h, "", "Rent", 9000)
    buy(client, h, "ICA", "Rice", 10)

    r = card(client, h)

    assert r["unknown"]["purchases"] == 1 and float(r["unknown"]["spend"]) == 9000.0
    assert r["named_spend"] == 10 and shop(r, "ICA")["share_pct"] == 100.0


def test_scope_narrows_it_like_the_other_dashboard_figures(user):
    client, h = user
    gid = client.post("/api/groups", json={"name": "Home"}, headers=h).json()["id"]
    buy(client, h, "Coop", "Tea", 40, group_id=gid)

    everything = card(client, h)
    personal = card(client, h, scope="personal")
    group = card(client, h, scope=str(gid))

    assert any(s["shop"] == "Coop" for s in everything["shops"])
    assert all(s["shop"] != "Coop" for s in personal["shops"])
    assert [s["shop"] for s in group["shops"]] == ["Coop"]
