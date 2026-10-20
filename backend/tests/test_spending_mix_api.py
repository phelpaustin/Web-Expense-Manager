import datetime as dt

import pytest

URL = "/api/analytics/spending-mix"


def day(n):
    return (dt.date.today() - dt.timedelta(days=n)).isoformat()


def spend(client, h, category, amount, when, **extra):
    r = client.post("/api/expenses", json={"date": when, "category": category, "description": extra.pop("description", category),
                                           "amount": str(amount), "currency": "SEK", **extra}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def template(client, h, item="Gym", amount="400", category="Health"):
    r = client.post("/api/recurring", json={"item": item, "amount": amount, "frequency": "Monthly", "category": category}, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()


def mix(client, h, **params):
    r = client.get(URL, params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# --- the link between a template and what it posts ---------------------------------------

def test_what_a_template_posts_is_linked_and_what_you_type_is_not(client, make_user):
    _, h = make_user()
    t = template(client, h)
    typed = spend(client, h, "Food", 50, day(3))

    assert client.post(f"/api/recurring/{t['id']}/apply", headers=h).status_code == 200

    items = client.get("/api/expenses", params={"page_size": 50}, headers=h).json()["items"]
    assert {e["description"]: e["recurring_template_id"] for e in items} == {"Gym": t["id"], "Food": None}
    assert typed["recurring_template_id"] is None


def test_apply_due_links_every_period_it_catches_up_on(client, make_user):
    from app.db import models
    from app.db.database import SessionLocal

    _, h = make_user()
    t = template(client, h)
    db = SessionLocal()
    try:
        row = db.get(models.RecurringTemplate, t["id"])
        row.last_applied = dt.date.today() - dt.timedelta(days=65)
        row.schedule_anchor = None
        db.commit()
    finally:
        db.close()

    applied = client.post("/api/recurring/apply-due", headers=h).json()["applied"]

    items = client.get("/api/expenses", params={"page_size": 50}, headers=h).json()["items"]
    assert applied >= 2 and len(items) == applied
    assert {e["recurring_template_id"] for e in items} == {t["id"]}


def test_a_client_cannot_make_an_expense_look_committed(client, make_user):
    _, h = make_user()
    t = template(client, h)

    r = client.post("/api/expenses", json={"date": day(2), "category": "Food", "description": "x", "amount": "10", "currency": "SEK",
                                           "recurring_template_id": t["id"]}, headers=h)

    assert r.status_code == 201 and r.json()["recurring_template_id"] is None
    e = r.json()
    assert client.put(f"/api/expenses/{e['id']}", json={"recurring_template_id": t["id"]}, headers=h).json()["recurring_template_id"] is None


def test_cancelling_a_template_keeps_its_past_payments_committed(client, make_user):
    _, h = make_user()
    t = template(client, h, amount="400")
    client.post(f"/api/recurring/{t['id']}/apply", headers=h)

    assert client.delete(f"/api/recurring/{t['id']}", headers=h).status_code in (200, 204)

    assert float(mix(client, h)["totals"]["committed"]) == 400.0


# --- the endpoint --------------------------------------------------------------------------

@pytest.fixture
def user(client, make_user):
    _, h = make_user()
    for i in range(9):                                   # ordinary groceries over the last ~100 days
        spend(client, h, "Groceries", 100 + 10 * (i % 5), day(8 + i * 11))
    spend(client, h, "Groceries", 3000, day(20), description="Party catering")
    t = template(client, h, amount="400")
    client.post(f"/api/recurring/{t['id']}/apply", headers=h)
    return client, h


def test_the_split_the_one_off_and_the_commitment(user):
    client, h = user

    r = mix(client, h)

    assert r["available"] is True and r["currency"] == "SEK" and r["unconverted_count"] == 0
    assert [(o["description"], float(o["amount"]), o["basis"]) for o in r["one_offs"]] == [("Party catering", 3000.0, "category")]
    assert float(r["totals"]["committed"]) == 400.0 and float(r["totals"]["one_off"]) == 3000.0
    t = r["totals"]
    assert round(float(t["committed"]) + float(t["everyday"]) + float(t["one_off"]), 2) == float(t["total"])
    assert [(c["description"], float(c["total"]), c["count"]) for c in r["committed_top"]] == [("Gym", 400.0, 1)]
    assert len(r["months"]) == 12 and r["months"][-1]["partial"] is True


def test_months_and_top_are_validated_and_respected(user):
    client, h = user
    assert len(mix(client, h, months=3)["months"]) == 3
    assert mix(client, h, top=1)["one_offs"][0]["description"] == "Party catering"
    for bad in ({"months": 0}, {"months": 13}, {"months": "x"}, {"top": 0}, {"top": 51}):
        assert client.get(URL, params=bad, headers=h).status_code == 422, bad


def test_it_needs_a_login_and_shows_only_your_own_spending(user, make_user):
    client, h = user
    _, other = make_user()

    assert client.get(URL).status_code == 401
    r = mix(client, other)
    assert r["available"] is False and r["one_offs"] == [] and r["committed_top"] == []
    assert mix(client, h)["available"] is True


def test_scope_narrows_it_like_the_other_dashboard_figures(user):
    client, h = user
    gid = client.post("/api/groups", json={"name": "Home"}, headers=h).json()["id"]
    spend(client, h, "Groceries", 77, day(2), group_id=gid)

    everything = mix(client, h)
    group = mix(client, h, scope=str(gid))
    personal = mix(client, h, scope="personal")

    assert float(group["totals"]["total"]) == 77.0
    assert float(everything["totals"]["total"]) == float(personal["totals"]["total"]) + 77.0
