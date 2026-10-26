import datetime as dt

from app.db import models
from app.db.database import SessionLocal

URL = "/api/analytics/recurring-costs"


def template(client, h, item, amount, frequency="Monthly", **extra):
    r = client.post("/api/recurring", json={"item": item, "amount": str(amount), "frequency": frequency, **extra}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"] if "id" in r.json() else r.json()["template"]["id"]


def posted(template_id, user_id, date, amount, currency="SEK"):
    with SessionLocal() as db:
        db.add(models.Expense(user_id=user_id, date=dt.date.fromisoformat(date), category="Subs", description="x", amount=amount,
                              currency=currency, price_per_unit=amount, recurring_template_id=template_id))
        db.commit()


def get(client, h):
    r = client.get(URL, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def uid(client, h):
    return client.get("/api/auth/me", headers=h).json()["id"]


def test_totals_for_the_users_templates(client, make_user):
    _, h = make_user()
    template(client, h, "Gym", 300); template(client, h, "Insurance", 1200, "Yearly")
    r = get(client, h)
    assert r["count"] == 2 and float(r["monthly_total"]) == 400.0 and float(r["yearly_total"]) == 4800.0
    assert [i["item"] for i in r["items"]] == ["Gym", "Insurance"]
    assert r["currency"] == "SEK" and r["unconverted_count"] == 0
    assert r["items"][0]["price_change"] is None


def test_nothing_recurring(client, make_user):
    _, h = make_user()
    r = get(client, h)
    assert r["count"] == 0 and r["items"] == [] and float(r["monthly_total"]) == 0.0


def test_a_price_rise_comes_from_what_was_posted(client, make_user):
    _, h = make_user()
    u = uid(client, h)
    t = template(client, h, "Netflix", 120)
    posted(t, u, "2026-08-01", 100); posted(t, u, "2026-09-01", 120)
    c = get(client, h)["items"][0]["price_change"]
    assert float(c["from"]) == 100.0 and float(c["to"]) == 120.0 and c["since"] == "2026-09-01" and c["direction"] == "up"
    assert get(client, h)["price_rises"] == 1


def test_the_template_s_own_amount_and_currency_are_reported(client, make_user):
    _, h = make_user()
    template(client, h, "Spotify", 10)
    i = get(client, h)["items"][0]
    assert float(i["monthly"]) == 10.0 and i["native_currency"] == "SEK" and float(i["native_amount"]) == 10.0


def test_needs_a_login(client):
    assert client.get(URL).status_code in (401, 403)


def test_each_person_sees_only_their_own(client, make_user):
    _, a = make_user(); _, b = make_user()
    ta = template(client, a, "Secret subscription", 999)
    posted(ta, uid(client, a), "2026-09-01", 999)
    template(client, b, "Mine", 5)
    seen = get(client, b)
    assert "Secret" not in str(seen) and seen["count"] == 1 and float(seen["monthly_total"]) == 5.0


def test_another_persons_payments_never_leak_into_a_price_change(client, make_user):
    _, a = make_user(); _, b = make_user()
    tb = template(client, b, "Mine", 5)
    # an expense of A that (wrongly) carries B's template id must not count for B
    posted(tb, uid(client, a), "2026-08-01", 50)
    posted(tb, uid(client, b), "2026-09-01", 5)
    assert get(client, b)["items"][0]["price_change"] is None
