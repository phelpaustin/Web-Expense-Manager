import datetime as dt

URL = "/api/analytics/unusual"


def day(n):
    return (dt.date.today() - dt.timedelta(days=n)).isoformat()


def add(client, h, amount, when, category="Food", description="x", shop="", **extra):
    r = client.post("/api/expenses", json={"date": when, "category": category, "description": description, "amount": str(amount),
                                           "shop": shop, "currency": "SEK", **extra}, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()


def history(client, h, n=10, category="Food"):
    for i in range(n):
        add(client, h, 100 + (i % 3) * 5, day(40 + i * 7), category=category)


def get(client, h, **params):
    r = client.get(URL, params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_an_unusually_big_expense_is_flagged(client, make_user):
    _, h = make_user()
    history(client, h)
    add(client, h, 450, day(3), description="Dinner out", shop="Fancy")
    r = get(client, h)
    [i] = r["unusual"]["items"]
    assert i["description"] == "Dinner out" and i["shop"] == "Fancy" and float(i["amount"]) == 450.0 and float(i["usual"]) == 105.0
    assert r["unusual"]["total_found"] == 1 and r["currency"] == "SEK" and r["unconverted_count"] == 0
    assert r["duplicates"]["items"] == []


def test_a_possible_duplicate_is_flagged(client, make_user):
    _, h = make_user()
    add(client, h, 59.9, day(2), description="Lunch", shop="Max")
    add(client, h, 59.9, day(2), description="Lunch", shop="Max")
    [d] = get(client, h)["duplicates"]["items"]
    assert d["count"] == 2 and float(d["amount"]) == 59.9 and len(d["ids"]) == 2 and d["shop"] == "Max"


def test_nothing_to_flag_in_ordinary_spending(client, make_user):
    _, h = make_user()
    history(client, h)
    add(client, h, 110, day(3))
    r = get(client, h)
    assert r["unusual"]["items"] == [] and r["duplicates"]["items"] == [] and r["unusual"]["checked"] == 1


def test_the_windows_and_limits(client, make_user):
    _, h = make_user()
    history(client, h)
    add(client, h, 450, day(45))
    assert get(client, h)["unusual"]["items"] == []                     # 45 days ago is outside the default 30
    assert len(get(client, h, recent_days=60)["unusual"]["items"]) == 1
    add(client, h, 5, day(70), description="Gum", shop="Kiosk"); add(client, h, 5, day(70), description="Gum", shop="Kiosk")
    assert get(client, h)["duplicates"]["items"] == []                  # 70 days ago is outside the default 60
    assert len(get(client, h, duplicate_days=90)["duplicates"]["items"]) == 1
    for bad in ({"recent_days": 0}, {"recent_days": 367}, {"duplicate_days": 0}, {"top": 0}, {"top": 51}, {"top": "x"}):
        assert client.get(URL, params=bad, headers=h).status_code == 422


def test_scope_personal_leaves_space_expenses_out(client, make_user):
    _, h = make_user()
    history(client, h)
    add(client, h, 450, day(3))
    assert len(get(client, h, scope="personal")["unusual"]["items"]) == 1
    assert len(get(client, h, scope="all")["unusual"]["items"]) == 1


def test_the_same_line_twice_on_one_receipt_is_not_a_duplicate(client, make_user):
    _, h = make_user()
    bill = client.post("/api/pending-bills", json={"date": day(3), "shop": "ICA", "amount": "40"}, headers=h).json()
    line = {"date": day(3), "category": "Food", "description": "Milk", "amount": "20", "shop": "ICA", "currency": "SEK"}
    r = client.post("/api/expenses/bulk", json={"items": [line, line], "bill_id": bill["id"]}, headers=h)
    assert r.status_code in (200, 201), r.text
    assert get(client, h)["duplicates"]["items"] == []
    add(client, h, 20, day(3), description="Milk", shop="ICA")        # typed in again by hand
    assert get(client, h)["duplicates"]["items"][0]["count"] == 2


def test_needs_a_login(client):
    assert client.get(URL).status_code in (401, 403)


def test_each_person_sees_only_their_own_spending(client, make_user):
    _, a = make_user(); _, b = make_user()
    history(client, a); add(client, a, 4500, day(3), description="Secret purchase", shop="Hidden")
    add(client, a, 5, day(2), description="Secret gum", shop="Hidden"); add(client, a, 5, day(2), description="Secret gum", shop="Hidden")
    seen = get(client, b)
    assert seen["unusual"]["items"] == [] and seen["duplicates"]["items"] == []
    assert "Secret" not in str(seen) and "Hidden" not in str(seen)
