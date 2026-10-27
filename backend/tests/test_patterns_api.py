import datetime as dt

from app.db import models
from app.db.database import SessionLocal

URL = "/api/analytics/patterns"


def day(n):
    return dt.date.today() - dt.timedelta(days=n)


def add(client, h, amount, when, **extra):
    body = {"date": when.isoformat(), "category": "Food", "description": "x", "amount": str(amount), "currency": "SEK", **extra}
    r = client.post("/api/expenses", json=body, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()


def get(client, h, **params):
    r = client.get(URL, params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def saturdays_heavy(client, h, weeks=12):
    """A 100 expense on every Saturday and a 5 one on every Wednesday of the last `weeks` weeks."""
    n = 0
    for i in range(weeks * 7 + 7):
        d = day(i)
        if d.weekday() == 5:
            add(client, h, 100, d); n += 1
        elif d.weekday() == 2:
            add(client, h, 5, d); n += 1
    return n


def test_shape_and_a_saturday_spender(client, make_user):
    _, h = make_user()
    saturdays_heavy(client, h)
    r = get(client, h)
    assert r["months"] == 6 and r["currency"] and r["unconverted_count"] == 0
    assert [w["name"] for w in r["weekdays"]] == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    assert [p["label"] for p in r["month_parts"]] == ["1–7", "8–14", "15–21", "22–31"]
    assert r["enough"] is True and r["busiest_weekday"] == "Saturday"
    sat = r["weekdays"][5]
    assert float(sat["per_day"]) > float(r["weekdays"][2]["per_day"]) > 0
    assert float(r["weekdays"][0]["total"]) == 0
    assert abs(sum(w["share_pct"] for w in r["weekdays"]) - 100) < 0.5


def test_too_little_history_is_not_enough(client, make_user):
    _, h = make_user()
    for i in range(3):
        add(client, h, 10, day(i))
    r = get(client, h)
    assert r["enough"] is False and r["busiest_weekday"] is None and r["count"] == 3


def test_the_window_follows_months(client, make_user):
    _, h = make_user()
    add(client, h, 10, day(100))                       # about 3 months ago
    assert get(client, h, months=1)["count"] == 0
    assert get(client, h, months=6)["count"] == 1
    assert get(client, h, months=12)["count"] == 1
    assert get(client, h, months=36)["start"] < get(client, h, months=6)["start"]


def test_months_must_be_between_1_and_36(client, make_user):
    _, h = make_user()
    for bad in (0, 37, "x"):
        assert client.get(URL, params={"months": bad}, headers=h).status_code == 422


def test_recurring_payments_are_left_out(client, make_user):
    uid, h = make_user()
    saturdays_heavy(client, h)
    before = get(client, h)
    r = client.post("/api/recurring", json={"item": "Rent", "amount": "9000", "frequency": "Monthly"}, headers=h)
    assert r.status_code == 201, r.text
    template_id = r.json()["id"] if "id" in r.json() else r.json()["template"]["id"]
    with SessionLocal() as db:                         # a payment the template posted
        db.add(models.Expense(user_id=uid, date=day(3), category="Housing", description="Rent", amount=9000, currency="SEK",
                              price_per_unit=9000, recurring_template_id=template_id))
        db.commit()
    after = get(client, h)
    assert after["spent"] == before["spent"] and after["count"] == before["count"]


def test_scope_personal_leaves_space_expenses_out(client, make_user):
    _, h = make_user()
    gid = client.post("/api/groups", json={"name": "G", "space_type": "household"}, headers=h).json()["id"]
    add(client, h, 50, day(1))
    add(client, h, 70, day(2), group_id=gid)
    assert get(client, h, scope="personal")["spent"] == 50.0
    assert get(client, h, scope="all")["spent"] == 120.0


def test_needs_a_login(client):
    assert client.get(URL).status_code in (401, 403)


def test_each_person_sees_only_their_own_spending(client, make_user):
    _, a = make_user(); _, b = make_user()
    saturdays_heavy(client, a)
    seen = get(client, b)
    assert seen["count"] == 0 and seen["spent"] == 0 and seen["enough"] is False
