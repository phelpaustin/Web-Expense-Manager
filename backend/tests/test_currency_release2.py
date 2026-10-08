"""Release 2: currencies are per record and default from the space / base currency."""
import datetime as dt
from decimal import Decimal

from app.db import models
from app.db.database import SessionLocal

TODAY = dt.date.today().isoformat()
# Fake rates (conftest): EUR->SEK = 10, every other supported pair = 0.5.


def _set_base(client, h, cur):
    assert client.post("/api/options/base-currency", json={"currency": cur}, headers=h).status_code == 200


def _expense(client, h, **kw):
    body = {"date": TODAY, "category": "Food", "amount": "10", **kw}
    r = client.post("/api/expenses", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


# ── defaults: expenses ───────────────────────────────────────────────────
def test_expense_defaults_to_base_currency(client, make_user):
    _, h = make_user()
    _set_base(client, h, "EUR")
    assert _expense(client, h)["currency"] == "EUR"
    assert _expense(client, h, currency="USD")["currency"] == "USD"  # explicit wins


def test_expense_in_space_defaults_to_space_currency(client, make_user):
    _, h = make_user()
    _set_base(client, h, "EUR")
    g = client.post("/api/groups", json={"name": "Flat", "space_type": "household", "currency": "usd"}, headers=h).json()
    assert g["currency"] == "USD"
    assert _expense(client, h, group_id=g["id"])["currency"] == "USD"
    assert _expense(client, h, group_id=g["id"], currency="SEK")["currency"] == "SEK"
    # bulk uses the same rule
    r = client.post("/api/expenses/bulk", json={"items": [{"date": TODAY, "category": "F", "amount": "1", "group_id": g["id"]}]}, headers=h)
    assert r.json()[0]["currency"] == "USD"


def test_import_without_currency_column_uses_base_currency(client, make_user):
    _, h = make_user()
    _set_base(client, h, "EUR")
    csv = f"Date,Category,Amount\n{TODAY},Food,5\n".encode()
    assert client.post("/api/expenses/import", files={"file": ("x.csv", csv, "text/csv")}, headers=h).json()["added"] == 1
    assert client.get("/api/expenses", headers=h).json()["items"][0]["currency"] == "EUR"


# ── spaces ───────────────────────────────────────────────────────────────
def test_space_currency_defaults_to_creators_base_currency_and_can_change(client, make_user):
    _, h = make_user()
    _set_base(client, h, "EUR")
    g = client.post("/api/groups", json={"name": "Biz", "space_type": "business"}, headers=h).json()
    assert g["currency"] == "EUR"
    exp = _expense(client, h, group_id=g["id"])
    r = client.put(f"/api/groups/{g['id']}", json={"name": "Biz", "currency": "SEK"}, headers=h)
    assert r.status_code == 200 and r.json()["currency"] == "SEK"
    # existing expenses keep their own currency; only new ones default to the new one
    listed = client.get(f"/api/expenses?scope={g['id']}", headers=h).json()["items"]
    assert [e["currency"] for e in listed if e["id"] == exp["id"]] == ["EUR"]
    assert _expense(client, h, group_id=g["id"])["currency"] == "SEK"
    assert client.get("/api/groups", headers=h).json()[0]["currency"] == "SEK"


def test_space_currency_must_be_convertible(client, make_user):
    _, h = make_user()
    assert client.post("/api/groups", json={"name": "X", "currency": "XXX"}, headers=h).status_code == 422


def test_trip_currency_defaults_to_base_currency(client, make_user):
    _, h = make_user()
    _set_base(client, h, "EUR")
    assert client.post("/api/trips", json={"name": "Rome"}, headers=h).json()["currency"] == "EUR"
    assert client.post("/api/trips", json={"name": "NYC", "currency": "USD"}, headers=h).json()["currency"] == "USD"


# ── recurring + bills inherit currency ───────────────────────────────────
def test_recurring_posts_in_its_own_currency(client, make_user):
    _, h = make_user()
    _set_base(client, h, "EUR")
    t = client.post("/api/recurring", json={"item": "Rent", "amount": "900", "frequency": "Monthly"}, headers=h).json()
    assert t["currency"] == "EUR"
    client.post(f"/api/recurring/{t['id']}/apply", headers=h)
    start = (dt.date.today() - dt.timedelta(days=75)).isoformat()
    client.post(f"/api/recurring/{t['id']}/backfill", json={"start_date": start, "end_date": (dt.date.today() - dt.timedelta(days=1)).isoformat()}, headers=h)
    items = client.get("/api/expenses?search=Rent", headers=h).json()["items"]
    assert len(items) >= 2
    assert {e["currency"] for e in items} == {"EUR"}


def test_recurring_currency_can_be_set_and_changed(client, make_user):
    _, h = make_user()
    t = client.post("/api/recurring", json={"item": "Gym", "amount": "30", "currency": "usd"}, headers=h).json()
    assert t["currency"] == "USD"
    assert client.put(f"/api/recurring/{t['id']}", json={"currency": "SEK"}, headers=h).json()["currency"] == "SEK"
    # an explicit null must not wipe the required field
    assert client.put(f"/api/recurring/{t['id']}", json={"currency": None}, headers=h).json()["currency"] == "SEK"
    client.post(f"/api/recurring/{t['id']}/apply", headers=h)
    assert client.get("/api/expenses?search=Gym", headers=h).json()["items"][0]["currency"] == "SEK"


def test_itemise_keeps_the_bills_currency(client, make_user):
    _, h = make_user()
    _set_base(client, h, "EUR")
    b = client.post("/api/pending-bills", json={"date": TODAY, "shop": "Hotel", "amount": "80", "currency": "USD"}, headers=h).json()
    assert b["currency"] == "USD"
    assert client.post(f"/api/pending-bills/{b['id']}/itemise", headers=h).status_code == 200
    e = client.get("/api/expenses?search=Hotel", headers=h).json()["items"][0]
    assert e["currency"] == "USD"
    d = client.post("/api/pending-bills", json={"date": TODAY, "shop": "Cafe", "amount": "5"}, headers=h).json()
    assert d["currency"] == "EUR"  # default = base


def test_ledger_converts_bills_into_base_currency(client, make_user):
    _, h = make_user()  # base SEK
    client.post("/api/pending-bills", json={"date": TODAY, "shop": "Hotel", "amount": "100", "currency": "EUR"}, headers=h)
    client.post("/api/bills-ledger/manual", json={"date": TODAY, "shop": "Rent", "amount": "20", "currency": "EUR"}, headers=h)
    rows = {r["shop"]: r for r in client.get("/api/bills-ledger", headers=h).json()}
    assert Decimal(str(rows["Hotel"]["amount"])) == Decimal("1000")  # 100 EUR * 10
    assert Decimal(str(rows["Rent"]["amount"])) == Decimal("200")
    assert rows["Hotel"]["currency"] == "SEK"


# ── income ───────────────────────────────────────────────────────────────
def test_income_currency_and_converted_summary(client, make_user):
    _, h = make_user()  # base SEK
    r = client.post("/api/income", json={"date": TODAY, "amount": "100", "source": "Job", "currency": "EUR"}, headers=h)
    assert r.json()["currency"] == "EUR"
    client.post("/api/income", json={"date": TODAY, "amount": "50", "source": "Gift"}, headers=h)  # default SEK
    assert client.get("/api/income", headers=h).json()[1]["currency"] == "SEK"
    summary = client.get("/api/income/summary", headers=h).json()
    assert Decimal(str(summary["total"])) == Decimal("1050")  # 100 EUR -> 1000 SEK, + 50 SEK
    m = client.get("/api/metrics", headers=h).json()
    assert Decimal(str(m["this_month_income"])) == Decimal("1050")


# ── budgets ──────────────────────────────────────────────────────────────
def test_budget_keeps_its_currency_when_base_currency_changes(client, make_user):
    _, h = make_user()  # base SEK
    r = client.put("/api/budgets", json={"category": "Food", "amount": "1000"}, headers=h)
    assert Decimal(str(r.json()["Food"])) == Decimal("1000")
    _set_base(client, h, "EUR")
    # 1000 SEK is shown as its EUR equivalent (fake rate 0.5), not reinterpreted as 1000 EUR
    assert Decimal(str(client.get("/api/budgets", headers=h).json()["Food"])) == Decimal("500")
    # a budget typed after the change is in the new base currency
    client.put("/api/budgets", json={"category": "Fun", "amount": "70"}, headers=h)
    assert Decimal(str(client.get("/api/budgets", headers=h).json()["Fun"])) == Decimal("70")


def test_budget_that_cannot_be_converted_is_omitted(client, make_user, monkeypatch):
    from app.core import fx
    uid, h = make_user()
    db = SessionLocal()
    db.add(models.Budget(user_id=uid, category="Odd", amount=100, currency="XXX"))
    db.commit()
    db.close()
    client.put("/api/budgets", json={"category": "Food", "amount": "10"}, headers=h)
    budgets = client.get("/api/budgets", headers=h).json()
    assert "Odd" not in budgets and "Food" in budgets


# ── options ──────────────────────────────────────────────────────────────
def test_options_list_selectable_currencies(client, make_user):
    _, h = make_user()
    cur = client.get("/api/options", headers=h).json()["currencies"]
    assert cur == ["EUR", "SEK", "USD"]
