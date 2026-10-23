import datetime as dt

import pytest

URL = "/api/analytics/forecast"


def month_back(n):
    """(year, month) n calendar months before this one."""
    t = dt.date.today()
    i = t.year * 12 + (t.month - 1) - n
    return i // 12, i % 12 + 1


def key(n):
    y, m = month_back(n)
    return f"{y:04d}-{m:02d}"


def spend(client, h, category, amount, back, day=5, **extra):
    y, m = month_back(back)
    r = client.post("/api/expenses", json={"date": f"{y:04d}-{m:02d}-{day:02d}", "category": category, "description": extra.pop("description", category),
                                           "amount": str(amount), "currency": "SEK", **extra}, headers=h)
    assert r.status_code == 201, r.text


def forecast(client, h, **params):
    r = client.get(URL, params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def user(client, make_user):
    """Eight finished months of ordinary spending, a one-off two months ago, and some this month."""
    _, h = make_user()
    for back in range(1, 9):
        spend(client, h, "Groceries", 400 + 10 * (back % 3), back, day=3)
        spend(client, h, "Groceries", 380 + 10 * (back % 4), back, day=17)
        spend(client, h, "Fun", 150, back, day=10)
    spend(client, h, "Electronics", 9000, 2, day=20, description="Laptop")
    spend(client, h, "Groceries", 420, 0, day=1)
    return client, h


def test_a_forecast_with_a_range_a_track_record_and_categories(user):
    client, h = user

    r = forecast(client, h)

    assert r["available"] is True and r["month"] == key(0) and r["currency"] == "SEK" and r["unconverted_count"] == 0
    f = r["forecast"]
    assert f["low"] is not None and f["low"] <= f["point"] <= f["high"]
    assert r["accuracy"]["months_tested"] == 4 and r["model"]["label"] and r["level"] == 80
    assert len(r["history"]) == 8 and r["history"][-1]["month"] == key(1)
    assert round(sum(c["forecast"] for c in r["categories"]), 2) == f["point"]
    assert {c["category"] for c in r["categories"]} == {"Groceries", "Fun"}


def test_a_one_off_is_kept_out_of_the_baseline_and_reported_beside_it(user):
    client, h = user

    r = forecast(client, h)

    laptop_month = next(m for m in r["history"] if m["month"] == key(2))
    assert laptop_month["one_off"] == 9000.0 and laptop_month["baseline"] < 1500
    assert r["one_offs"]["months_with_one_offs"] == 1 and r["one_offs"]["average_per_month"] == pytest.approx(9000 / 8, abs=0.01)
    assert r["forecast"]["point"] < 1500                                   # not inflated by the laptop
    assert r["so_far"]["total"] == 420.0 and r["so_far"]["day"] == dt.date.today().day


def test_a_new_user_gets_a_reason_not_an_error(client, make_user):
    _, h = make_user()

    nothing = forecast(client, h)
    spend(client, h, "Food", 50, 1)
    spend(client, h, "Food", 50, 2)
    two = forecast(client, h)

    assert (nothing["available"], nothing["reason"]) == (False, "no_spending")
    assert (two["available"], two["reason"], two["months_available"]) == (False, "not_enough_history", 2)


def test_top_is_validated_and_respected(user):
    client, h = user
    assert len(forecast(client, h, top=1)["categories"]) == 2          # one named category plus the roll-up
    assert forecast(client, h, top=1)["categories"][-1]["rollup"] is True
    for bad in (0, 21, -1, "x"):
        assert client.get(URL, params={"top": bad}, headers=h).status_code == 422, bad


def test_it_needs_a_login_and_shows_only_your_own_spending(user, make_user):
    client, h = user
    _, other = make_user()

    assert client.get(URL).status_code == 401
    assert forecast(client, other)["available"] is False
    assert forecast(client, h)["available"] is True


def test_scope_narrows_it_like_the_other_dashboard_figures(user):
    client, h = user
    gid = client.post("/api/groups", json={"name": "Home"}, headers=h).json()["id"]
    for back in range(1, 6):
        spend(client, h, "Shared", 1000, back, day=12, group_id=gid)

    shared = forecast(client, h, scope=str(gid))
    personal = forecast(client, h, scope="personal")

    assert {c["category"] for c in shared["categories"]} == {"Shared"}
    assert "Shared" not in {c["category"] for c in personal["categories"]}


# --- the old forecast is gone ---------------------------------------------------------------

def test_the_trends_payload_no_longer_carries_the_old_single_number_forecast(user):
    client, h = user

    trends = client.get("/api/analytics/trends", headers=h).json()

    assert "forecast_next_month" not in trends and "forecast_available" not in trends
    assert {"monthly", "change", "current_month"} <= set(trends)


def test_the_dashboard_payload_does_not_compute_it_either(user):
    client, h = user

    dash = client.get("/api/dashboard", headers=h).json()

    assert "forecast_next_month" not in dash["trends"] and "forecast_available" not in dash["trends"]
