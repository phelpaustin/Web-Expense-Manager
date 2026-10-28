import datetime as dt

from app.db import models
from app.db.database import SessionLocal

URL = "/api/savings-goals"
TODAY = dt.date.today()


def day(n):
    return (TODAY - dt.timedelta(days=n)).isoformat()


def ahead(n):
    return (TODAY + dt.timedelta(days=n)).isoformat()


def make(client, h, name="Trip", target=1000, **extra):
    r = client.post(URL, json={"name": name, "target_amount": str(target), **extra}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def deposit(client, h, goal_id, amount, when=None, expect=201, **extra):
    body = {"amount": str(amount), **({"date": when} if when else {}), **extra}
    r = client.post(f"{URL}/{goal_id}/contributions", json=body, headers=h)
    assert r.status_code == expect, r.text
    return r.json()


def listing(client, h):
    r = client.get(URL, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# ── goals ──

def test_create_a_goal_and_see_it_listed(client, make_user):
    _, h = make_user()
    g = make(client, h, "New bike", 5000, target_date=ahead(200), note="  for commuting  ", currency="EUR")
    assert (g["name"], g["target_amount"], g["currency"], g["note"], g["target_date"]) == ("New bike", 5000, "EUR", "for commuting", ahead(200))
    assert (g["saved"], g["remaining"], g["pct"], g["status"], g["contributions"]) == (0, 5000, 0.0, "behind", [])
    out = listing(client, h)
    assert [x["id"] for x in out["goals"]] == [g["id"]] and out["summary"] == {"goals": 1, "reached": 0, "behind": 1} and out["limit"] == 50
    assert "contributions" not in out["goals"][0]


def test_the_currency_defaults_to_the_users_own(client, make_user):
    _, h = make_user()
    base = client.get("/api/options", headers=h).json()["base_currency"]
    assert make(client, h)["currency"] == base


def test_no_date_means_no_deadline(client, make_user):
    _, h = make_user()
    g = make(client, h)
    assert g["target_date"] is None and g["status"] == "no_deadline" and g["days_left"] is None


def test_a_goal_is_checked(client, make_user):
    _, h = make_user()
    bad = [{"name": ""}, {"name": "   "}, {"name": "x" * 121}, {"target_amount": "0"}, {"target_amount": "-5"}, {"target_amount": "0.001"},
           {"target_amount": "10000000000"}, {"target_amount": "x"}, {"currency": "ZZZ"}, {"target_date": "tomorrow"}]
    for change in bad:
        body = {"name": "Trip", "target_amount": "100", **change}
        assert client.post(URL, json=body, headers=h).status_code == 422, change
    assert client.post(URL, json={"target_amount": "1"}, headers=h).status_code == 422
    assert client.post(URL, json={"name": "Trip"}, headers=h).status_code == 422
    assert listing(client, h)["goals"] == []


def test_a_name_of_exactly_120_characters_is_fine(client, make_user):
    _, h = make_user()
    assert make(client, h, "x" * 120)["name"] == "x" * 120


def test_at_most_50_goals(client, make_user):
    _, h = make_user()
    for i in range(50):
        make(client, h, f"Goal {i}")
    r = client.post(URL, json={"name": "One more", "target_amount": "1"}, headers=h)
    assert r.status_code == 400 and "50" in r.json()["detail"]
    assert len(listing(client, h)["goals"]) == 50


def test_edit_a_goal(client, make_user):
    _, h = make_user()
    g = make(client, h, "Trip", 1000, target_date=ahead(100), note="a")
    r = client.put(f"{URL}/{g['id']}", json={"name": " Holiday ", "target_amount": "2000", "note": ""}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["name"], body["target_amount"], body["note"], body["target_date"]) == ("Holiday", 2000, "", ahead(100))   # left alone: the date
    r = client.put(f"{URL}/{g['id']}", json={"target_date": None}, headers=h)
    assert r.json()["target_date"] is None and r.json()["status"] == "no_deadline"           # null removes the date
    assert client.put(f"{URL}/{g['id']}", json={}, headers=h).json()["name"] == "Holiday"   # nothing sent, nothing changed


def test_an_edit_is_checked(client, make_user):
    _, h = make_user()
    g = make(client, h)
    for change in ({"name": None}, {"name": ""}, {"target_amount": None}, {"target_amount": 0}, {"currency": None}, {"currency": "ZZZ"}, {"note": None}):
        assert client.put(f"{URL}/{g['id']}", json=change, headers=h).status_code == 422, change
    assert client.get(f"{URL}/{g['id']}", headers=h).json()["name"] == "Trip"


def test_the_currency_can_change_until_money_is_added(client, make_user):
    _, h = make_user()
    g = make(client, h, currency="SEK")
    assert client.put(f"{URL}/{g['id']}", json={"currency": "EUR"}, headers=h).json()["currency"] == "EUR"
    deposit(client, h, g["id"], 100)
    assert client.put(f"{URL}/{g['id']}", json={"currency": "EUR"}, headers=h).status_code == 200           # the same one is no change
    r = client.put(f"{URL}/{g['id']}", json={"currency": "USD"}, headers=h)
    assert r.status_code == 400 and "currency" in r.json()["detail"].lower()
    assert client.get(f"{URL}/{g['id']}", headers=h).json()["currency"] == "EUR"


def test_delete_a_goal_and_its_deposits(client, make_user):
    uid, h = make_user()
    g = make(client, h)
    deposit(client, h, g["id"], 100); deposit(client, h, g["id"], 50)
    assert client.delete(f"{URL}/{g['id']}", headers=h).status_code == 204
    assert client.get(f"{URL}/{g['id']}", headers=h).status_code == 404 and listing(client, h)["goals"] == []
    with SessionLocal() as db:
        assert db.query(models.SavingsContribution).filter_by(user_id=uid).count() == 0


# ── deposits and withdrawals ──

def test_deposit_and_progress(client, make_user):
    _, h = make_user()
    g = make(client, h, target=1000)
    body = deposit(client, h, g["id"], 250, day(3), note="  birthday money ")
    assert (body["saved"], body["remaining"], body["pct"], body["contribution_count"], body["last_contribution"]) == (250, 750, 25.0, 1, day(3))
    assert [(c["date"], c["amount"], c["note"]) for c in body["contributions"]] == [(day(3), 250, "birthday money")]
    assert client.get(f"{URL}/{g['id']}", headers=h).json()["saved"] == 250
    assert listing(client, h)["goals"][0]["saved"] == 250


def test_the_date_defaults_to_today_and_is_not_set_in_the_future(client, make_user):
    _, h = make_user()
    g = make(client, h)
    assert deposit(client, h, g["id"], 10)["contributions"][0]["date"] == TODAY.isoformat()
    deposit(client, h, g["id"], 10, ahead(1))                                       # a day of slack for someone ahead of the server's clock
    r = client.post(f"{URL}/{g['id']}/contributions", json={"amount": "10", "date": ahead(2)}, headers=h)
    assert r.status_code == 422 and "future" in r.json()["detail"]
    assert client.get(f"{URL}/{g['id']}", headers=h).json()["contribution_count"] == 2


def test_contributions_are_listed_newest_first(client, make_user):
    _, h = make_user()
    g = make(client, h)
    deposit(client, h, g["id"], 1, day(10)); deposit(client, h, g["id"], 2, day(2)); deposit(client, h, g["id"], 3, day(5))
    assert [c["amount"] for c in client.get(f"{URL}/{g['id']}", headers=h).json()["contributions"]] == [2, 3, 1]


def test_a_withdrawal_takes_money_back_out(client, make_user):
    _, h = make_user()
    g = make(client, h)
    deposit(client, h, g["id"], 500, day(5))
    body = deposit(client, h, g["id"], -200, day(1))
    assert body["saved"] == 300 and body["contribution_count"] == 2


def test_you_cannot_take_out_more_than_is_saved(client, make_user):
    _, h = make_user()
    g = make(client, h)
    r = client.post(f"{URL}/{g['id']}/contributions", json={"amount": "-1"}, headers=h)
    assert r.status_code == 400 and "more than has been saved" in r.json()["detail"]
    deposit(client, h, g["id"], 100)
    assert client.post(f"{URL}/{g['id']}/contributions", json={"amount": "-100.01"}, headers=h).status_code == 400
    assert deposit(client, h, g["id"], -100)["saved"] == 0                            # all of it is fine


def test_a_deposit_is_checked(client, make_user):
    _, h = make_user()
    g = make(client, h)
    for bad in ({"amount": "0"}, {"amount": "0.001"}, {"amount": "x"}, {"amount": "10000000000"}, {"amount": "-10000000000"}, {"amount": "5", "date": "nope"}, {}):
        assert client.post(f"{URL}/{g['id']}/contributions", json=bad, headers=h).status_code == 422, bad
    assert client.post(f"{URL}/{g['id']}/contributions", json={"amount": "5", "note": "x" * 1001}, headers=h).status_code == 422


def test_amounts_are_kept_to_the_cent(client, make_user):
    _, h = make_user()
    g = make(client, h)
    deposit(client, h, g["id"], "10.005")
    deposit(client, h, g["id"], "0.10")
    deposit(client, h, g["id"], "0.20")
    assert client.get(f"{URL}/{g['id']}", headers=h).json()["saved"] == 10.3           # 10.005 became 10.00


def test_reaching_the_goal(client, make_user):
    _, h = make_user()
    g = make(client, h, target=300, target_date=ahead(60))
    deposit(client, h, g["id"], 100, day(30))
    body = deposit(client, h, g["id"], 200, day(1))
    assert (body["reached"], body["status"], body["pct"], body["remaining"]) == (True, "reached", 100.0, 0)
    assert listing(client, h)["summary"] == {"goals": 1, "reached": 1, "behind": 0}


def test_the_pace_and_the_projection_show_up(client, make_user):
    _, h = make_user()
    g = make(client, h, target=1000, target_date=ahead(365))
    body = deposit(client, h, g["id"], 300, day(30))
    assert body["recent_per_month"] > 0 and body["projected_date"] is not None and body["status"] == "on_track"
    assert body["needed_per_month"] is not None and body["days_left"] == 365


def test_delete_a_deposit(client, make_user):
    _, h = make_user()
    g = make(client, h)
    deposit(client, h, g["id"], 100, day(5))
    two = deposit(client, h, g["id"], 50, day(2))
    cid = two["contributions"][0]["id"]
    r = client.delete(f"{URL}/{g['id']}/contributions/{cid}", headers=h)
    assert r.status_code == 200 and r.json()["saved"] == 100 and r.json()["contribution_count"] == 1


def test_a_deposit_that_later_withdrawals_depend_on_cannot_be_removed(client, make_user):
    _, h = make_user()
    g = make(client, h)
    first = deposit(client, h, g["id"], 100, day(5))["contributions"][0]["id"]
    deposit(client, h, g["id"], -80, day(1))
    r = client.delete(f"{URL}/{g['id']}/contributions/{first}", headers=h)
    assert r.status_code == 400 and "withdrawals" in r.json()["detail"]
    assert client.get(f"{URL}/{g['id']}", headers=h).json()["saved"] == 20


def test_a_withdrawal_can_be_removed_to_put_the_money_back(client, make_user):
    _, h = make_user()
    g = make(client, h)
    deposit(client, h, g["id"], 100, day(5))
    w = deposit(client, h, g["id"], -80, day(1))["contributions"][0]["id"]
    assert client.delete(f"{URL}/{g['id']}/contributions/{w}", headers=h).json()["saved"] == 100


def test_removing_something_that_is_not_there(client, make_user):
    _, h = make_user()
    g, other = make(client, h), make(client, h, "Other")
    cid = deposit(client, h, other["id"], 10)["contributions"][0]["id"]
    assert client.delete(f"{URL}/{g['id']}/contributions/{cid}", headers=h).status_code == 404        # it belongs to another goal
    assert client.delete(f"{URL}/{g['id']}/contributions/99999", headers=h).status_code == 404
    assert client.get(f"{URL}/{other['id']}", headers=h).json()["saved"] == 10


def test_a_goal_holds_at_most_2000_deposits(client, make_user, monkeypatch):
    from app.api import savings_goals as api
    monkeypatch.setattr(api, "MAX_CONTRIBUTIONS", 3)
    _, h = make_user()
    g = make(client, h)
    for _ in range(3):
        deposit(client, h, g["id"], 1)
    r = client.post(f"{URL}/{g['id']}/contributions", json={"amount": "1"}, headers=h)
    assert r.status_code == 400 and "3" in r.json()["detail"]


# ── the list ──

def test_goals_are_listed_unfinished_first_nearest_date_first(client, make_user):
    _, h = make_user()
    done = make(client, h, "Done", 100)
    deposit(client, h, done["id"], 100)
    someday = make(client, h, "Someday", 100)
    later = make(client, h, "Later", 100, target_date=ahead(300))
    soon = make(client, h, "Soon", 100, target_date=ahead(30))
    assert [g["name"] for g in listing(client, h)["goals"]] == ["Soon", "Later", "Someday", "Done"]


def test_the_list_gives_each_goal_its_own_deposits(client, make_user):
    _, h = make_user()
    a, b = make(client, h, "A"), make(client, h, "B")
    deposit(client, h, a["id"], 10); deposit(client, h, a["id"], 5); deposit(client, h, b["id"], 7)
    saved = {g["name"]: (g["saved"], g["contribution_count"]) for g in listing(client, h)["goals"]}
    assert saved == {"A": (15, 2), "B": (7, 1)}


def test_an_overdue_goal_is_flagged(client, make_user):
    _, h = make_user()
    g = make(client, h, target=1000, target_date=day(10))
    deposit(client, h, g["id"], 100, day(20))
    out = listing(client, h)
    assert out["goals"][0]["status"] == "overdue" and out["summary"]["behind"] == 1


# ── who can see what ──

def test_needs_a_login(client):
    assert client.get(URL).status_code in (401, 403)
    assert client.post(URL, json={"name": "x", "target_amount": "1"}).status_code in (401, 403)


def test_each_person_sees_and_changes_only_their_own_goals(client, make_user):
    _, a = make_user(); _, b = make_user()
    g = make(client, a, "Secret goal")
    deposit(client, a, g["id"], 100)
    assert listing(client, b)["goals"] == []
    for call in (
        lambda: client.get(f"{URL}/{g['id']}", headers=b),
        lambda: client.put(f"{URL}/{g['id']}", json={"name": "Mine now"}, headers=b),
        lambda: client.delete(f"{URL}/{g['id']}", headers=b),
        lambda: client.post(f"{URL}/{g['id']}/contributions", json={"amount": "5"}, headers=b),
        lambda: client.delete(f"{URL}/{g['id']}/contributions/1", headers=b),
    ):
        assert call().status_code == 404
    after = client.get(f"{URL}/{g['id']}", headers=a).json()
    assert after["name"] == "Secret goal" and after["saved"] == 100 and after["contribution_count"] == 1
    assert "Secret" not in str(listing(client, b))


def test_unknown_goal_is_404(client, make_user):
    _, h = make_user()
    assert client.get(f"{URL}/99999", headers=h).status_code == 404
    assert client.delete(f"{URL}/99999", headers=h).status_code == 404


def test_deleting_an_account_removes_its_goals_and_deposits_but_not_anyone_elses(client, make_user):
    uid, h = make_user()
    other, oh = make_user()
    mine = make(client, h, "Mine"); theirs = make(client, oh, "Theirs")
    deposit(client, h, mine["id"], 10); deposit(client, h, mine["id"], 5); deposit(client, oh, theirs["id"], 7)
    assert client.post("/api/auth/delete-account", json={"password": "correct-horse-battery"}, headers=h).status_code == 204
    with SessionLocal() as db:
        assert db.query(models.SavingsGoal).filter_by(user_id=uid).count() == 0
        assert db.query(models.SavingsContribution).filter_by(user_id=uid).count() == 0
        assert db.query(models.SavingsGoal).filter_by(user_id=other).count() == 1
        assert db.query(models.SavingsContribution).filter_by(user_id=other).count() == 1
    assert listing(client, oh)["goals"][0]["saved"] == 7
