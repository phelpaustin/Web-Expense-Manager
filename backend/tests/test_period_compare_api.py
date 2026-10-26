import datetime as dt

URL = "/api/analytics/compare"


def month_back(n):
    t = dt.date.today()
    i = t.year * 12 + (t.month - 1) - n
    return i // 12, i % 12 + 1


def key(n):
    y, m = month_back(n)
    return f"{y:04d}-{m:02d}"


def spend(client, h, back, amount, day=5, **extra):
    y, m = month_back(back)
    r = client.post("/api/expenses", json={"date": f"{y:04d}-{m:02d}-{day:02d}", "category": "Food", "description": "x",
                                           "amount": str(amount), "currency": "SEK", **extra}, headers=h)
    assert r.status_code == 201, r.text


def get(client, h, **params):
    r = client.get(URL, params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_defaults_to_the_last_finished_month(client, make_user):
    _, h = make_user()
    spend(client, h, 2, 1000); spend(client, h, 1, 1500)
    r = get(client, h)
    assert r["month"] == key(1) and r["partial"] is False and float(r["total"]) == 1500.0
    last = next(c for c in r["comparisons"] if c["key"] == "last_month")
    assert last["month"] == key(2) and float(last["change"]) == 500.0 and last["direction"] == "up"
    assert r["currency"] == "SEK" and r["unconverted_count"] == 0


def test_a_chosen_month_and_a_bad_one(client, make_user):
    _, h = make_user()
    spend(client, h, 2, 1000)
    assert get(client, h, month=key(2))["month"] == key(2)
    assert client.get(URL, params={"month": "2026-13"}, headers=h).status_code == 422
    assert client.get(URL, params={"month": "september"}, headers=h).status_code == 422


def test_needs_a_login(client):
    assert client.get(URL).status_code in (401, 403)


def test_each_person_sees_only_their_own_spending(client, make_user):
    _, a = make_user(); _, b = make_user()
    spend(client, a, 2, 1000); spend(client, a, 1, 4000)
    spend(client, b, 2, 10); spend(client, b, 1, 20)
    assert float(get(client, a)["total"]) == 4000.0
    assert float(get(client, b)["total"]) == 20.0


def test_scope_personal_leaves_space_expenses_out(client, make_user):
    _, h = make_user()
    spend(client, h, 2, 1000); spend(client, h, 1, 1500)
    r = get(client, h, scope="personal")
    assert float(r["total"]) == 1500.0
