import datetime as dt

import pytest

URL = "/api/analytics/category-change"


def month_back(n):
    """(year, month) n calendar months before this one."""
    t = dt.date.today()
    i = t.year * 12 + (t.month - 1) - n
    return i // 12, i % 12 + 1


def key(n):
    y, m = month_back(n)
    return f"{y:04d}-{m:02d}"


def spend(client, h, back, category, amount, day=5, **extra):
    y, m = month_back(back)
    r = client.post("/api/expenses", json={"date": f"{y:04d}-{m:02d}-{day:02d}", "category": category, "description": "x",
                                           "amount": str(amount), "currency": "SEK", **extra}, headers=h)
    assert r.status_code == 201, r.text


@pytest.fixture
def user(client, make_user):
    _, h = make_user()
    # two months ago -> last month: Groceries +800, Dining +300, Transport new +100
    spend(client, h, 2, "Groceries", 1000); spend(client, h, 2, "Dining", 200)
    spend(client, h, 1, "Groceries", 1800); spend(client, h, 1, "Dining", 500); spend(client, h, 1, "Transport", 100)
    return client, h


def get(client, h, **params):
    r = client.get(URL, params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_defaults_to_the_last_finished_month_against_the_one_before(user):
    client, h = user

    r = get(client, h)

    assert (r["month"], r["compare_month"], r["partial"]) == (key(1), key(2), False)
    assert float(r["total"]["change"]) == 1200.0 and r["total"]["direction"] == "up"
    assert [(c["category"], float(c["change"])) for c in r["categories"]] == [("Groceries", 800.0), ("Dining", 300.0), ("Transport", 100.0)]
    assert r["currency"] == "SEK" and r["unconverted_count"] == 0
    assert r["months"] == [key(2), key(1)]


def test_a_chosen_month_and_the_number_of_categories_shown(user):
    client, h = user

    r = get(client, h, month=key(1), top=2)

    assert [c["category"] for c in r["categories"]] == ["Groceries", "Dining"]
    assert r["other"]["count"] == 1 and float(r["other"]["change"]) == 100.0


def test_the_month_in_progress_is_compared_like_for_like(client, make_user):
    _, h = make_user()
    today = dt.date.today()
    spend(client, h, 1, "Food", 100, day=1)
    if today.day < 28:  # (every month has at least 28 days)
        spend(client, h, 1, "Food", 9999, day=today.day + 1)  # later in the month than we are now: left out
    y, m = month_back(0)
    client.post("/api/expenses", json={"date": f"{y:04d}-{m:02d}-01", "category": "Food", "description": "x", "amount": "130", "currency": "SEK"}, headers=h)

    r = get(client, h, month=key(0))

    assert r["partial"] is True and r["through_day"] == today.day
    assert float(r["total"]["before"]) == 100.0 and float(r["total"]["change"]) == 30.0


def test_a_month_with_no_spending_is_unavailable_not_an_error(user):
    client, h = user

    r = get(client, h, month="2001-01")

    assert r["available"] is False and r["categories"] == []


@pytest.mark.parametrize("bad", ["2026-13", "2026-00", "26-09", "september", "2026-9", "", "2026-09-01"])
def test_a_malformed_month_is_rejected(user, bad):
    client, h = user
    assert client.get(URL, params={"month": bad}, headers=h).status_code == 422


@pytest.mark.parametrize("top", [0, 51, -1, "x"])
def test_top_must_be_between_1_and_50(user, top):
    client, h = user
    assert client.get(URL, params={"top": top}, headers=h).status_code == 422


def test_it_needs_a_login_and_only_ever_shows_your_own_spending(user, make_user):
    client, h = user
    _, other = make_user()

    assert client.get(URL).status_code == 401
    r = get(client, other)
    assert r["available"] is False and r["categories"] == [] and r["months"] == []
    assert get(client, h)["available"] is True


def test_scope_narrows_it_like_every_other_dashboard_figure(user):
    client, h = user
    gid = client.post("/api/groups", json={"name": "Home"}, headers=h).json()["id"]
    y, m = month_back(1)
    client.post("/api/expenses", json={"date": f"{y:04d}-{m:02d}-06", "category": "Groceries", "description": "shared", "amount": "400",
                                       "currency": "SEK", "group_id": gid}, headers=h)

    personal = get(client, h, scope="personal")
    group = get(client, h, scope=str(gid))

    assert float(personal["total"]["change"]) == 1200.0
    assert float(group["total"]["now"]) == 400.0


def test_case_variants_of_a_category_are_one_category(client, make_user):
    _, h = make_user()
    spend(client, h, 2, "Milk", 100)
    spend(client, h, 1, "milk", 150)   # stored as "Milk": categories are case-insensitive now
    spend(client, h, 1, "MILK", 50)

    r = get(client, h)

    assert [(c["category"], float(c["before"]), float(c["now"])) for c in r["categories"]] == [("Milk", 100.0, 200.0)]
