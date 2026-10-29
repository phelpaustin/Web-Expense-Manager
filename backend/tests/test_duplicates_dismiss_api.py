import datetime as dt

from app.db import models
from app.db.database import SessionLocal

URL = "/api/analytics/unusual"
DISMISS = "/api/analytics/duplicates/dismiss"


def day(n):
    return (dt.date.today() - dt.timedelta(days=n)).isoformat()


def add(client, h, amount, when, description="Lunch", shop="Max", **extra):
    r = client.post("/api/expenses", json={"date": when, "category": "Food", "description": description, "amount": str(amount),
                                           "shop": shop, "currency": "SEK", **extra}, headers=h)
    assert r.status_code in (200, 201), r.text


def twice(client, h, when=None, **kw):
    when = when or day(2)
    add(client, h, 60, when, **kw)
    add(client, h, 60, when, **kw)


def duplicates(client, h, **params):
    r = client.get(URL, params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["duplicates"]


def dismiss(client, h, item, count=None):
    return client.post(DISMISS, json={"key": item["key"], "day": item["date"], "count": count or item["count"]}, headers=h)


def stored(user_id=None):
    with SessionLocal() as db:
        q = db.query(models.DismissedDuplicate)
        return (q.filter_by(user_id=user_id) if user_id else q).all()


def test_dismissing_a_group_takes_it_off_the_list(client, make_user):
    _, h = make_user()
    twice(client, h)
    [item] = duplicates(client, h)["items"]
    r = dismiss(client, h, item)
    assert r.status_code == 200 and r.json() == {"dismissed": True, "key": item["key"], "count": 2}
    d = duplicates(client, h)
    assert d["items"] == [] and d["total_found"] == 0
    assert [x["key"] for x in d["dismissed"]] == [item["key"]] and d["dismissed_total"] == 1


def test_it_stays_off_the_list_after_reloading(client, make_user):
    _, h = make_user()
    twice(client, h)
    dismiss(client, h, duplicates(client, h)["items"][0])
    for _ in range(3):
        assert duplicates(client, h)["items"] == []


def test_undoing_brings_it_back(client, make_user):
    uid, h = make_user()
    twice(client, h)
    item = duplicates(client, h)["items"][0]
    dismiss(client, h, item)
    assert client.delete(f"{DISMISS}/{item['key']}", headers=h).status_code == 204
    d = duplicates(client, h)
    assert [x["key"] for x in d["items"]] == [item["key"]] and d["items"][0]["was_dismissed"] is False and d["dismissed"] == []
    assert stored(uid) == []


def test_one_more_lookalike_entry_brings_it_back_and_can_be_dismissed_again(client, make_user):
    uid, h = make_user()
    twice(client, h)
    dismiss(client, h, duplicates(client, h)["items"][0])
    add(client, h, 60, day(2))
    [item] = duplicates(client, h)["items"]
    assert item["count"] == 3 and item["was_dismissed"] is True
    dismiss(client, h, item)
    assert duplicates(client, h)["items"] == []
    assert [r.count for r in stored(uid)] == [3]                       # the same row, updated


def test_dismissing_twice_keeps_one_row(client, make_user):
    uid, h = make_user()
    twice(client, h)
    item = duplicates(client, h)["items"][0]
    assert dismiss(client, h, item).status_code == 200 and dismiss(client, h, item).status_code == 200
    assert len(stored(uid)) == 1


def test_removing_an_entry_does_not_bring_it_back(client, make_user):
    _, h = make_user()
    twice(client, h)
    add(client, h, 60, day(2))
    item = duplicates(client, h)["items"][0]
    dismiss(client, h, item)                                         # count 3
    ids = item["ids"]
    assert client.delete(f"/api/expenses/{ids[0]}", headers=h).status_code in (200, 204)
    assert duplicates(client, h)["items"] == []                      # 2 entries left, fewer than were dismissed


def test_only_the_person_who_dismissed_it_stops_seeing_it(client, make_user):
    a_id, a = make_user(); _, b = make_user()
    twice(client, a); twice(client, b)                               # the same entries, the same key, two users
    item = duplicates(client, a)["items"][0]
    assert item["key"] == duplicates(client, b)["items"][0]["key"]
    dismiss(client, a, item)
    assert duplicates(client, a)["items"] == []
    assert len(duplicates(client, b)["items"]) == 1 and duplicates(client, b)["dismissed"] == []
    assert client.delete(f"{DISMISS}/{item['key']}", headers=b).status_code == 204     # B undoing nothing changes nothing for A
    assert len(stored(a_id)) == 1


def test_a_dismissed_group_outside_the_window_is_not_listed(client, make_user):
    _, h = make_user()
    twice(client, h, when=day(70))
    r = client.get(URL, params={"duplicate_days": 90}, headers=h).json()["duplicates"]
    dismiss(client, h, r["items"][0])
    assert client.get(URL, headers=h).json()["duplicates"]["dismissed"] == []
    assert len(client.get(URL, params={"duplicate_days": 90}, headers=h).json()["duplicates"]["dismissed"]) == 1


def test_a_dismissal_that_matches_nothing_is_harmless(client, make_user):
    _, h = make_user()
    r = client.post(DISMISS, json={"key": "a" * 64, "day": day(1), "count": 2}, headers=h)
    assert r.status_code == 200
    assert duplicates(client, h)["items"] == [] and duplicates(client, h)["dismissed"] == []


def test_undoing_something_never_dismissed_is_fine(client, make_user):
    _, h = make_user()
    assert client.delete(f"{DISMISS}/{'b' * 64}", headers=h).status_code == 204


def test_the_request_is_checked(client, make_user):
    _, h = make_user()
    good = {"key": "c" * 64, "day": day(1), "count": 2}
    assert client.post(DISMISS, json=good, headers=h).status_code == 200
    for change in ({"key": "short"}, {"key": "C" * 64}, {"key": "g" * 64}, {"key": "c" * 65}, {"count": 1}, {"count": 0}, {"count": 1001},
                   {"day": "nope"}, {"day": None}, {"count": "x"}):
        assert client.post(DISMISS, json={**good, **change}, headers=h).status_code == 422, change
    assert client.post(DISMISS, json={"key": "c" * 64, "day": day(1)}, headers=h).status_code == 422
    for bad in ("short", "G" * 64, "c" * 63):
        assert client.delete(f"{DISMISS}/{bad}", headers=h).status_code in (404, 422), bad


def test_there_is_a_limit_but_existing_ones_can_still_be_updated(client, make_user, monkeypatch):
    from app.api import analytics
    monkeypatch.setattr(analytics, "MAX_DISMISSED", 2)
    _, h = make_user()
    for ch in "ab":
        assert client.post(DISMISS, json={"key": ch * 64, "day": day(1), "count": 2}, headers=h).status_code == 200
    r = client.post(DISMISS, json={"key": "c" * 64, "day": day(1), "count": 2}, headers=h)
    assert r.status_code == 400 and "up to 2" in r.json()["detail"]
    assert client.post(DISMISS, json={"key": "a" * 64, "day": day(1), "count": 3}, headers=h).status_code == 200


def test_dismissals_of_groups_too_old_to_show_again_are_dropped(client, make_user):
    uid, h = make_user()
    old = (dt.date.today() - dt.timedelta(days=500)).isoformat()
    assert client.post(DISMISS, json={"key": "d" * 64, "day": old, "count": 2}, headers=h).status_code == 200
    assert len(stored(uid)) == 1                                     # nothing prunes on the call that adds it... the next call does
    assert client.post(DISMISS, json={"key": "e" * 64, "day": day(1), "count": 2}, headers=h).status_code == 200
    assert [r.key for r in stored(uid)] == ["e" * 64]


def test_needs_a_login(client):
    assert client.post(DISMISS, json={"key": "a" * 64, "day": day(1), "count": 2}).status_code in (401, 403)
    assert client.delete(f"{DISMISS}/{'a' * 64}").status_code in (401, 403)


def test_deleting_an_account_removes_its_dismissals_but_not_anyone_elses(client, make_user):
    uid, h = make_user(); other, oh = make_user()
    for who, hh in ((uid, h), (other, oh)):
        assert client.post(DISMISS, json={"key": "a" * 64, "day": day(1), "count": 2}, headers=hh).status_code == 200
    assert client.post("/api/auth/delete-account", json={"password": "correct-horse-battery"}, headers=h).status_code == 204
    assert stored(uid) == [] and len(stored(other)) == 1
