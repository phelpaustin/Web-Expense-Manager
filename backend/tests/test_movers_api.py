import datetime as dt

URL = "/api/analytics/movers"


def month_back(n):
    t = dt.date.today()
    i = t.year * 12 + (t.month - 1) - n
    return i // 12, i % 12 + 1


def key(n):
    y, m = month_back(n)
    return f"{y:04d}-{m:02d}"


def spend(client, h, back, amount, category="Food", shop="", description="x", **extra):
    y, m = month_back(back)
    r = client.post("/api/expenses", json={"date": f"{y:04d}-{m:02d}-05", "category": category, "shop": shop,
                                           "description": description, "amount": str(amount), "currency": "SEK", **extra}, headers=h)
    assert r.status_code == 201, r.text


def get(client, h, **params):
    r = client.get(URL, params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def names(rows):
    return [r["name"] for r in rows]


def test_defaults_to_the_last_finished_month(client, make_user):
    _, h = make_user()
    spend(client, h, 2, 100, "Food", "Lidl"); spend(client, h, 1, 300, "Food", "Lidl"); spend(client, h, 1, 80, "Pets", "Zoo")
    r = get(client, h)
    assert r["month"] == key(1) and r["compare_month"] == key(2) and r["available"] is True
    assert names(r["categories"]["rose"]) == ["Food"] and names(r["categories"]["new"]) == ["Pets"]
    assert names(r["shops"]["rose"]) == ["Lidl"] and names(r["shops"]["new"]) == ["Zoo"]
    assert r["currency"] == "SEK" and r["unconverted_count"] == 0


def test_shop_merges_are_followed(client, make_user):
    _, h = make_user()
    spend(client, h, 2, 100, "Food", "ICA Maxi"); spend(client, h, 1, 100, "Food", "ICA")
    assert client.post("/api/aliases/merge", json={"kind": "shop", "names": ["ICA Maxi"], "canonical": "ICA"}, headers=h).status_code in (200, 201)
    r = get(client, h)
    assert names(r["shops"]["new"]) == [] and names(r["shops"]["fell"]) == [] and names(r["shops"]["rose"]) == []


def test_a_bill_total_counts_towards_its_shop(client, make_user):
    _, h = make_user()
    spend(client, h, 2, 100, "Food", "Lidl")
    y, m = month_back(1)
    r = client.post("/api/pending-bills", json={"date": f"{y:04d}-{m:02d}-05", "shop": "Lidl", "amount": "400"}, headers=h)
    assert r.status_code == 201, r.text
    rose = get(client, h)["shops"]["rose"]
    assert names(rose) == ["Lidl"] and float(rose[0]["change"]) == 300.0


def test_a_chosen_month_the_limit_and_bad_input(client, make_user):
    _, h = make_user()
    spend(client, h, 3, 100); spend(client, h, 2, 200)
    assert get(client, h, month=key(2))["month"] == key(2)
    assert client.get(URL, params={"month": "2026-13"}, headers=h).status_code == 422
    assert client.get(URL, params={"top": 0}, headers=h).status_code == 422
    assert client.get(URL, params={"top": 21}, headers=h).status_code == 422


def test_needs_a_login(client):
    assert client.get(URL).status_code in (401, 403)


def test_each_person_sees_only_their_own_spending(client, make_user):
    _, a = make_user(); _, b = make_user()
    spend(client, a, 2, 100, "Food", "Lidl"); spend(client, a, 1, 900, "Secret", "A-only shop")
    spend(client, b, 2, 10, "Food", "Coop"); spend(client, b, 1, 20, "Food", "Coop")
    seen = get(client, b)
    text = str(seen)
    assert "Secret" not in text and "A-only shop" not in text and "Lidl" not in text
    assert names(seen["shops"]["rose"]) == ["Coop"]


def test_scope_personal_leaves_space_expenses_out(client, make_user):
    _, h = make_user()
    spend(client, h, 2, 100, "Food", "Lidl"); spend(client, h, 1, 300, "Food", "Lidl")
    assert names(get(client, h, scope="personal")["shops"]["rose"]) == ["Lidl"]
    assert float(get(client, h, scope="personal")["categories"]["rose"][0]["change"]) == 200.0
