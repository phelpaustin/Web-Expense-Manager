import datetime as dt

URL = "/api/analytics/price-trends/cheapest-shops"


def day(n):
    return (dt.date.today() - dt.timedelta(days=n)).isoformat()


def buy(client, h, item, price, shop, when, qty=1, unit="Litre", category="Food", brand=""):
    r = client.post(
        "/api/expenses",
        json={"date": when, "category": category, "description": item, "amount": str(price), "quantity": qty, "unit": unit,
              "shop": shop, "brand": brand, "currency": "SEK"},
        headers=h,
    )
    assert r.status_code in (200, 201), r.text


def get(client, h, **params):
    r = client.get(URL, params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def milk(client, h):
    buy(client, h, "Milk", 15, "ICA", day(40)); buy(client, h, "Milk", 15, "ICA", day(30)); buy(client, h, "Milk", 12, "Lidl", day(20))


def test_finds_the_cheaper_shop(client, make_user):
    _, h = make_user()
    milk(client, h)
    r = get(client, h)
    [m] = r["items"]
    assert m["item"] == "Milk" and m["cheapest"]["shop"] == "Lidl" and m["usual"]["shop"] == "ICA"
    assert float(m["saving_per_unit"]) == 3.0 and m["saving_pct"] == 20.0
    assert r["currency"] == "SEK" and r["months"] == 12 and r["compared"] == 1


def test_the_price_is_per_unit_not_per_purchase(client, make_user):
    _, h = make_user()
    # 2 litres for 30 = 15 per litre at ICA; 1 litre for 12 at Lidl
    buy(client, h, "Milk", 30, "ICA", day(40), qty=2); buy(client, h, "Milk", 30, "ICA", day(30), qty=2)
    buy(client, h, "Milk", 12, "Lidl", day(20), qty=1)
    [m] = get(client, h)["items"]
    assert float(m["usual"]["avg_price"]) == 15.0 and float(m["cheapest"]["avg_price"]) == 12.0


def test_months_limits_how_far_back_it_looks(client, make_user):
    _, h = make_user()
    buy(client, h, "Milk", 15, "ICA", day(400)); buy(client, h, "Milk", 15, "ICA", day(395)); buy(client, h, "Milk", 12, "Lidl", day(390))
    assert get(client, h)["compared"] == 0                      # all more than a year ago
    assert len(get(client, h, months=0)["items"]) == 1
    assert len(get(client, h, months=24)["items"]) == 1


def test_top_and_bad_input(client, make_user):
    _, h = make_user()
    milk(client, h)
    assert client.get(URL, params={"top": 0}, headers=h).status_code == 422
    assert client.get(URL, params={"top": 51}, headers=h).status_code == 422
    assert client.get(URL, params={"months": -1}, headers=h).status_code == 422
    assert client.get(URL, params={"months": "x"}, headers=h).status_code == 422


def test_shop_merges_are_followed(client, make_user):
    _, h = make_user()
    buy(client, h, "Milk", 15, "ICA Maxi", day(40)); buy(client, h, "Milk", 15, "ICA", day(30)); buy(client, h, "Milk", 12, "Lidl", day(20))
    assert client.post("/api/aliases/merge", json={"kind": "shop", "names": ["ICA Maxi"], "canonical": "ICA"}, headers=h).status_code in (200, 201)
    [m] = get(client, h)["items"]
    assert m["usual"]["shop"] == "ICA" and m["usual"]["times_bought"] == 2


def test_needs_a_login(client):
    assert client.get(URL).status_code in (401, 403)


def test_each_person_sees_only_their_own_purchases(client, make_user):
    _, a = make_user(); _, b = make_user()
    milk(client, a)
    buy(client, a, "Secret item", 50, "Hidden shop", day(10)); buy(client, a, "Secret item", 40, "Other hidden", day(9))
    seen = get(client, b)
    assert seen["items"] == [] and seen["compared"] == 0
    assert "Secret" not in str(seen) and "Hidden" not in str(seen)
