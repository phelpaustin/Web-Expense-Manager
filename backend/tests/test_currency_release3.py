"""Release 3: display currency, dated budgets, trip settlement without 503s."""
import datetime as dt
from decimal import Decimal

from app.db import models
from app.db.database import SessionLocal

TODAY = dt.date.today().isoformat()
# Fake rates (conftest): EUR->SEK = 10, every other supported pair = 0.5.


def _opts(client, h):
    return client.get("/api/options", headers=h).json()


def _set_display(client, h, cur):
    r = client.post("/api/options/display-currency", json={"currency": cur}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _expense(client, h, **kw):
    r = client.post("/api/expenses", json={"date": TODAY, "category": "Food", "amount": "100", **kw}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


# ── display currency ─────────────────────────────────────────────────────
def test_display_currency_follows_base_until_chosen(client, make_user):
    _, h = make_user()
    o = _opts(client, h)
    assert (o["base_currency"], o["display_currency"], o["display_currency_is_custom"]) == ("SEK", "SEK", False)
    client.post("/api/options/base-currency", json={"currency": "EUR"}, headers=h)
    o = _opts(client, h)
    assert (o["base_currency"], o["display_currency"]) == ("EUR", "EUR")  # still following base

    o = _set_display(client, h, "usd")
    assert (o["base_currency"], o["display_currency"], o["display_currency_is_custom"]) == ("EUR", "USD", True)
    client.post("/api/options/base-currency", json={"currency": "SEK"}, headers=h)
    o = _opts(client, h)
    assert (o["base_currency"], o["display_currency"]) == ("SEK", "USD")  # custom display unaffected

    o = _set_display(client, h, None)  # reset
    assert (o["display_currency"], o["display_currency_is_custom"]) == ("SEK", False)


def test_display_currency_must_be_convertible(client, make_user):
    _, h = make_user()
    assert client.post("/api/options/display-currency", json={"currency": "XXX"}, headers=h).status_code == 422


def test_totals_are_shown_in_display_currency_and_data_is_untouched(client, make_user):
    _, h = make_user()  # base SEK
    _expense(client, h, currency="SEK", amount="100")
    assert Decimal(str(client.get("/api/expenses/summary", headers=h).json()["total"])) == Decimal("100")
    _set_display(client, h, "EUR")
    s = client.get("/api/expenses/summary", headers=h).json()
    assert s["currency"] == "EUR" and Decimal(str(s["total"])) == Decimal("50")  # 100 SEK * 0.5
    # stored expense is exactly as entered
    item = client.get("/api/expenses", headers=h).json()["items"][0]
    assert (Decimal(str(item["amount"])), item["currency"]) == (Decimal("100"), "SEK")
    _set_display(client, h, None)
    assert Decimal(str(client.get("/api/expenses/summary", headers=h).json()["total"])) == Decimal("100")


def test_new_records_still_default_to_base_not_display(client, make_user):
    _, h = make_user()
    client.post("/api/options/base-currency", json={"currency": "EUR"}, headers=h)
    _set_display(client, h, "USD")
    assert _expense(client, h)["currency"] == "EUR"
    assert client.post("/api/recurring", json={"item": "Gym", "amount": "5"}, headers=h).json()["currency"] == "EUR"
    assert client.post("/api/income", json={"date": TODAY, "amount": "5", "source": "x"}, headers=h).json()["currency"] == "EUR"
    assert client.post("/api/pending-bills", json={"date": TODAY, "shop": "s", "amount": "5"}, headers=h).json()["currency"] == "EUR"


def test_income_metrics_and_ledger_use_display_currency(client, make_user):
    _, h = make_user()  # base SEK
    client.post("/api/income", json={"date": TODAY, "amount": "100", "source": "Job", "currency": "EUR"}, headers=h)
    client.post("/api/pending-bills", json={"date": TODAY, "shop": "Hotel", "amount": "100", "currency": "EUR"}, headers=h)
    _set_display(client, h, "USD")
    assert Decimal(str(client.get("/api/income/summary", headers=h).json()["total"])) == Decimal("50")  # EUR->USD 0.5
    ledger = {r["shop"]: r for r in client.get("/api/bills-ledger", headers=h).json()}
    assert Decimal(str(ledger["Hotel"]["amount"])) == Decimal("50") and ledger["Hotel"]["currency"] == "USD"


# ── budgets ──────────────────────────────────────────────────────────────
def test_budget_defaults_to_display_currency_and_accepts_an_explicit_one(client, make_user):
    _, h = make_user()  # base SEK
    _set_display(client, h, "EUR")
    # typed in the currency budgets are shown in (EUR): stored as 100 EUR, shown as 100
    client.put("/api/budgets", json={"category": "Food", "amount": "100"}, headers=h)
    # explicitly in USD while displaying EUR: 100 USD -> 50 EUR
    client.put("/api/budgets", json={"category": "Fun", "amount": "100", "currency": "usd"}, headers=h)
    budgets = client.get("/api/budgets", headers=h).json()
    assert Decimal(str(budgets["Food"])) == Decimal("100")
    assert Decimal(str(budgets["Fun"])) == Decimal("50")
    db = SessionLocal()
    stored = {b.category: b.currency for b in db.query(models.Budget).all() if b.category in ("Food", "Fun")}
    db.close()
    assert stored["Fun"] == "USD"
    # switching display currency converts, it never reinterprets
    _set_display(client, h, "SEK")
    budgets = client.get("/api/budgets", headers=h).json()
    assert Decimal(str(budgets["Fun"])) == Decimal("50")  # USD->SEK is 0.5 in the fake rates


def test_budget_currency_must_be_convertible(client, make_user):
    _, h = make_user()
    r = client.put("/api/budgets", json={"category": "Food", "amount": "1", "currency": "XXX"}, headers=h)
    assert r.status_code == 422


def test_past_month_budgets_use_that_months_rate_current_uses_latest(client, make_user, monkeypatch):
    from app.core import fx

    _, h = make_user()  # base SEK
    client.put("/api/budgets", json={"category": "Food", "amount": "100", "currency": "EUR"}, headers=h)
    seen = []
    real = fx.get_rate
    monkeypatch.setattr(fx, "get_rate", lambda a, b, on=None: seen.append((a, b, on)) or real(a, b, on))

    client.get("/api/budgets/status?month=2026-01", headers=h)
    assert ("EUR", "SEK", dt.date(2026, 1, 31)) in seen  # month end, dated

    seen.clear()
    client.get("/api/budgets/status", headers=h)
    assert ("EUR", "SEK", None) in seen  # current period: latest rate


# ── trips ────────────────────────────────────────────────────────────────
def _trip_with_expenses(client, h, uid, bad_currency=False):
    trip = client.post("/api/trips", json={"name": "Rome", "currency": "USD"}, headers=h).json()
    client.post("/api/expenses", json={"date": TODAY, "category": "Food", "amount": "100", "currency": "EUR", "group_id": trip["id"]}, headers=h)
    if bad_currency:
        db = SessionLocal()
        db.add(models.Expense(user_id=uid, group_id=trip["id"], date=dt.date.today(), category="Food",
                              description="Gold coin", amount=3, currency="XXX"))
        db.commit()
        db.close()
    return trip


def test_trip_summary_survives_an_unconvertible_expense(client, make_user):
    uid, h = make_user()
    trip = _trip_with_expenses(client, h, uid, bad_currency=True)
    r = client.get(f"/api/trips/{trip['id']}/summary", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["unconverted_count"] == 1
    assert Decimal(str(body["total_spent"])) == Decimal("50")  # only the convertible expense


def test_settlement_names_the_unconvertible_expense_instead_of_failing(client, make_user):
    uid, h = make_user()
    trip = _trip_with_expenses(client, h, uid, bad_currency=True)
    r = client.get(f"/api/trips/{trip['id']}/settlement", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["complete"] is False
    assert body["transactions"] == [] and body["per_member"] == []
    assert [e["description"] for e in body["unconverted_expenses"]] == ["Gold coin"]
    assert body["unconverted_expenses"][0]["currency"] == "XXX"
    assert "exchange rate" in body["message"]


def test_settlement_is_complete_when_everything_converts(client, make_user):
    uid, h = make_user()
    trip = _trip_with_expenses(client, h, uid)
    body = client.get(f"/api/trips/{trip['id']}/settlement", headers=h).json()
    assert body["complete"] is True
    assert Decimal(str(body["total_spent"])) == Decimal("50")
    assert "unconverted_expenses" not in body


# ── helpers ──────────────────────────────────────────────────────────────
def test_convert_rows_can_target_a_specific_currency(client, make_user):
    from app.api.options import convert_rows

    uid, h = make_user()
    _set_display(client, h, "USD")
    db = SessionLocal()
    rows = [{"date": dt.date.today(), "amount": Decimal("100"), "currency": "EUR"}]
    to_default = convert_rows(db, uid, rows)[0][0]
    to_sek = convert_rows(db, uid, rows, target="SEK")[0][0]
    db.close()
    assert (to_default["currency"], Decimal(str(to_default["amount"]))) == ("USD", Decimal("50"))
    assert (to_sek["currency"], Decimal(str(to_sek["amount"]))) == ("SEK", Decimal("1000"))
