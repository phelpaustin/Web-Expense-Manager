"""Subscription finder endpoints: find, ignore, track as recurring."""
import datetime as dt
import io
import json
import zipfile

from app.db import models
from app.db.database import SessionLocal
from tests.test_bill_sync import _insert, _legacy_bill

TODAY = dt.date.today()


def _months_back(n):
    """The same day of the month as today (kept <= 28), n months ago."""
    month_index = TODAY.year * 12 + TODAY.month - 1 - n
    y, m = divmod(month_index, 12)
    return dt.date(y, m + 1, min(TODAY.day, 28))


def _charges(uid, shop, amounts, **kw):
    """One charge per month, the last one this month, oldest first."""
    rows = [{"date": _months_back(len(amounts) - 1 - i).isoformat(), "amount": a, "shop": shop, "category": "Fun", **kw}
            for i, a in enumerate(amounts)]
    return _insert(uid, rows)


def _get(client, h):
    r = client.get("/api/subscriptions", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_repeating_charge_is_found_with_its_cost(client, make_user):
    uid, h = make_user()
    _charges(uid, "Spotify", [119] * 6)
    _insert(uid, [{"shop": "Lidl", "amount": 80, "date": TODAY.isoformat()}])
    data = _get(client, h)
    [s] = data["items"]
    assert (s["name"], s["frequency"], s["charges"]) == ("Spotify", "Monthly", 6)
    assert float(s["monthly"]) == 119 and float(s["yearly"]) == 1428
    assert float(data["monthly_total"]) == 119 and float(data["yearly_total"]) == 1428
    assert data["count"] == 1 and data["currency"] and data["unconverted_count"] == 0


def test_a_price_rise_shows_up(client, make_user):
    uid, h = make_user()
    _charges(uid, "Netflix", [109, 109, 109, 109, 129, 129])
    [s] = _get(client, h)["items"]
    assert s["price_change"]["direction"] == "up" and float(s["price_change"]["to"]) == 129


def test_items_of_a_multi_item_bill_are_not_subscriptions(client, make_user):
    uid, h = make_user()
    ids = _charges(uid, "Lidl", [60, 60, 60, 60])
    # Each month's charge is one of two items on a shared bill: groceries, not a subscription.
    more = _charges(uid, "Lidl", [40, 40, 40, 40], description="second item")
    for n, (a, b) in enumerate(zip(ids, more)):
        _legacy_bill(uid, [a, b], shop="Lidl", date=_months_back(3 - n).isoformat())
    assert _get(client, h)["items"] == []


def test_expenses_in_a_space_and_other_users_data_are_left_out(client, make_user):
    uid, h = make_user()
    other, _ = make_user()
    _charges(other, "Theirs", [50] * 5)
    _charges(uid, "Shared", [70] * 5, group_id=999999)
    assert _get(client, h)["items"] == []


def test_a_recurring_payment_already_set_up_is_counted_but_not_listed(client, make_user):
    uid, h = make_user()
    _charges(uid, "Spotify", [119] * 6)
    assert client.post("/api/recurring", json={"item": "spotify", "amount": "119", "frequency": "Monthly"}, headers=h).status_code == 201
    data = _get(client, h)
    assert data["items"] == [] and data["tracked_count"] == 1


def test_not_a_subscription_hides_it_and_can_be_undone(client, make_user):
    uid, h = make_user()
    _charges(uid, "Coffee Bar", [30] * 5)
    assert client.post("/api/subscriptions/ignore", json={"name": "Coffee  BAR"}, headers=h).status_code == 204
    assert client.post("/api/subscriptions/ignore", json={"name": "coffee bar"}, headers=h).status_code == 204  # twice is fine
    data = _get(client, h)
    assert data["items"] == [] and data["ignored"] == [{"key": "coffee bar", "name": "Coffee BAR"}]
    assert client.post("/api/subscriptions/unignore", json={"name": "Coffee Bar"}, headers=h).status_code == 204
    data = _get(client, h)
    assert [i["name"] for i in data["items"]] == ["Coffee Bar"] and data["ignored"] == []


def test_ignoring_is_per_user(client, make_user):
    uid, h = make_user()
    uid2, h2 = make_user()
    _charges(uid, "Gym", [300] * 5)
    _charges(uid2, "Gym", [300] * 5)
    client.post("/api/subscriptions/ignore", json={"name": "Gym"}, headers=h)
    assert _get(client, h)["items"] == [] and len(_get(client, h2)["items"]) == 1


def test_a_stopped_subscription_is_listed_apart(client, make_user):
    uid, h = make_user()
    rows = [{"date": _months_back(8 - i).isoformat(), "amount": 250, "shop": "Old gym"} for i in range(4)]
    _insert(uid, rows)
    data = _get(client, h)
    assert data["items"] == [] and [s["name"] for s in data["stopped"]] == ["Old gym"]


def test_input_is_validated_and_needs_a_login(client, make_user):
    _, h = make_user()
    assert client.post("/api/subscriptions/ignore", json={"name": ""}, headers=h).status_code == 422
    assert client.post("/api/subscriptions/ignore", json={}, headers=h).status_code == 422
    assert client.get("/api/subscriptions").status_code == 401
    assert client.post("/api/subscriptions/ignore", json={"name": "x"}).status_code == 401


def test_tracking_a_found_subscription_starts_the_schedule_after_the_last_charge(client, make_user):
    uid, h = make_user()
    last = _months_back(0)
    body = {"item": "Spotify", "amount": "119", "frequency": "Monthly", "last_applied": last.isoformat()}
    r = client.post("/api/recurring", json=body, headers=h)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["last_applied"] == last.isoformat()
    assert t["due"] is False  # the charge on that day is not posted again; the next one is a month away
    future = {**body, "last_applied": (TODAY + dt.timedelta(days=3)).isoformat()}
    assert client.post("/api/recurring", json=future, headers=h).status_code == 422


def test_ignored_names_travel_with_a_backup(client, make_user):
    uid, h = make_user()
    client.post("/api/subscriptions/ignore", json={"name": "Coffee Bar"}, headers=h)
    zdata = client.get("/api/backup", headers=h).content
    assert json.loads(zipfile.ZipFile(io.BytesIO(zdata)).read("backup.json"))["ignored_subscriptions"] == [{"key": "coffee bar", "name": "Coffee Bar"}]
    _, h2 = make_user()
    from app.core.rate_limit import limiter
    limiter.reset()
    assert client.post("/api/backup/restore", files={"file": ("b.zip", zdata, "application/zip")}, headers=h2).status_code == 200
    assert _get(client, h2)["ignored"] == [{"key": "coffee bar", "name": "Coffee Bar"}]


def test_deleting_the_account_removes_ignored_names(client, make_user):
    uid, h = make_user()
    client.post("/api/subscriptions/ignore", json={"name": "Coffee Bar"}, headers=h)
    assert client.post("/api/auth/delete-account", json={"password": "correct-horse-battery"}, headers=h).status_code == 204
    db = SessionLocal()
    assert db.query(models.IgnoredSubscription).filter_by(user_id=uid).count() == 0
    db.close()
