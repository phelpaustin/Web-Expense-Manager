"""The combined /api/dashboard endpoint returns exactly what the separate endpoints do."""
import datetime as dt
from decimal import Decimal

import pytest

from app.logic import currency as currency_logic

TODAY = dt.date.today()


def _seed(client, h):
    gid = client.post("/api/groups", json={"name": "Household"}, headers=h).json()["id"]
    rows = [
        # personal, three currencies, several months
        {"date": str(TODAY), "category": "Groceries", "amount": "120.50", "currency": "SEK"},
        {"date": str(TODAY - dt.timedelta(days=40)), "category": "Groceries", "amount": "80", "currency": "USD"},
        {"date": str(TODAY - dt.timedelta(days=75)), "category": "Transport", "amount": "30.25", "currency": "EUR"},
        {"date": str(TODAY - dt.timedelta(days=110)), "category": "Dine-Out", "amount": "55", "currency": "SEK"},
        {"date": str(TODAY - dt.timedelta(days=150)), "category": "Dine-Out", "amount": "70", "currency": "SEK"},
        # shared space
        {"date": str(TODAY - dt.timedelta(days=2)), "category": "Household", "amount": "300", "currency": "SEK", "group_id": gid},
    ]
    for r in rows:
        assert client.post("/api/expenses", json=r, headers=h).status_code == 201
    client.post("/api/income", json={"date": str(TODAY), "amount": "5000", "source": "Salary", "currency": "SEK"}, headers=h)
    client.put("/api/budgets", json={"category": "__total_monthly__", "amount": "400", "currency": "SEK"}, headers=h)
    client.put("/api/budgets", json={"category": "Groceries", "amount": "100", "currency": "SEK"}, headers=h)
    return gid


def _separate(client, h, query):
    def get(path):
        r = client.get(path + query, headers=h)
        assert r.status_code == 200, (path, r.text)
        return r.json()

    return {
        "summary": get("/api/expenses/summary"),
        "trends": get("/api/analytics/trends"),
        "categories": get("/api/analytics/categories"),
        "budgets": get("/api/budgets/status"),
        "metrics": get("/api/metrics"),
        "period_status": get("/api/budgets/period-status"),
        "budget_risk": get("/api/budgets/risk"),
    }


@pytest.mark.parametrize("scope", ["", "scope=all", "scope=personal", "scope={gid}", "space_ids=personal,{gid}", "scope=9999"])
def test_dashboard_matches_the_separate_endpoints(client, make_user, scope):
    _, h = make_user()
    gid = _seed(client, h)
    query = ("?" + scope.format(gid=gid)) if scope else ""

    combined = client.get("/api/dashboard" + query, headers=h)
    assert combined.status_code == 200, combined.text
    body = combined.json()

    expected = _separate(client, h, query)
    expected["alerts"] = client.get("/api/alerts", headers=h).json()  # alerts always cover every space
    # category_months exists only on the combined endpoint (it feeds the period picker); it is
    # checked separately below.
    months = body.pop("category_months")
    assert body == expected

    # Its rows add up to the all-time category totals the breakdown already shows.
    per_category = {}
    for row in months:
        per_category[row["category"]] = per_category.get(row["category"], Decimal(0)) + Decimal(str(row["total"]))
    assert {c: float(t) for c, t in per_category.items()} == pytest.approx(
        {c["category"]: float(c["total"]) for c in expected["categories"]}
    )
    assert [r["month"] for r in months] == sorted(r["month"] for r in months)


def test_category_months_groups_by_calendar_month_and_category():
    from app.logic import analytics as analytics_logic

    rows = [
        {"date": dt.date(2026, 1, 5), "category": "Groceries", "amount": Decimal("10.00")},
        {"date": dt.date(2026, 1, 20), "category": "Groceries", "amount": Decimal("5.50")},
        {"date": dt.date(2026, 1, 21), "category": "Rent", "amount": Decimal("100")},
        {"date": dt.date(2026, 2, 1), "category": "Groceries", "amount": Decimal("7")},
    ]
    out = analytics_logic.category_by_month(rows)
    assert [(r["month"], r["category"], float(r["total"])) for r in out] == [
        ("2026-01", "Groceries", 15.5),
        ("2026-01", "Rent", 100.0),
        ("2026-02", "Groceries", 7.0),
    ]
    assert analytics_logic.category_by_month([]) == []


def test_alerts_can_be_left_out(client, make_user):
    _, h = make_user()
    _seed(client, h)
    body = client.get("/api/dashboard?include_alerts=false", headers=h).json()
    assert body["alerts"] is None
    assert body["summary"]["count"] > 0


def test_dashboard_for_a_user_with_no_data(client, make_user):
    _, h = make_user()
    body = client.get("/api/dashboard", headers=h).json()
    assert body["summary"]["count"] == 0
    assert body["categories"] == []
    assert body["category_months"] == []
    assert body["alerts"] == []
    assert body["budget_risk"]["has_budgets"] is False and body["budget_risk"]["items"] == []


def test_dashboard_never_includes_another_users_expenses(client, make_user):
    _, mine = make_user()
    _, other = make_user()
    client.post("/api/expenses", json={"date": str(TODAY), "category": "Food", "amount": "10", "currency": "SEK"}, headers=mine)
    client.post("/api/expenses", json={"date": str(TODAY), "category": "Food", "amount": "999", "currency": "SEK"}, headers=other)
    assert client.get("/api/dashboard", headers=mine).json()["summary"]["total"] == 10


def test_dashboard_requires_login(client):
    assert client.get("/api/dashboard").status_code == 401


# ── currency conversion: same results, far fewer rate lookups ─────────────
def test_conversion_looks_up_each_currency_and_day_once():
    calls = []

    def rate(src, dst, day):
        calls.append((src, dst, day))
        return Decimal("2") if src != dst else Decimal("1")

    day = dt.date(2026, 1, 5)
    rows = [{"date": day, "amount": Decimal("1.10"), "price_per_unit": Decimal("1.1000"), "currency": "USD"} for _ in range(50)]
    rows += [{"date": day, "amount": Decimal("3"), "currency": "SEK"} for _ in range(50)]
    out, skipped = currency_logic.convert_expenses_partial(rows, "SEK", rate)
    assert skipped == 0 and len(out) == 100
    assert len(calls) == 2
    assert out[0]["amount"] == Decimal("2.20") and out[0]["original_amount"] == Decimal("1.10")
    assert out[0]["price_per_unit"] == Decimal("2.2000") and out[0]["currency"] == "SEK"
    assert out[60]["amount"] == Decimal("3.00")


def test_unconvertible_rows_are_skipped_and_counted():
    rate = lambda src, dst, day: None if src == "XYZ" else Decimal("1")  # noqa: E731
    rows = [
        {"date": dt.date(2026, 1, 1), "amount": Decimal("5"), "currency": "SEK"},
        {"date": dt.date(2026, 1, 1), "amount": Decimal("5"), "currency": "XYZ"},   # no rate
        {"date": dt.date(2026, 1, 1), "amount": Decimal("5"), "currency": "12"},    # not a currency code
    ]
    out, skipped = currency_logic.convert_expenses_partial(rows, "SEK", rate)
    assert [r["currency"] for r in out] == ["SEK"] and skipped == 2


def test_convert_expenses_still_raises_when_a_rate_is_missing():
    with pytest.raises(currency_logic.CurrencyConversionUnavailable):
        currency_logic.convert_expenses(
            [{"date": dt.date(2026, 1, 1), "amount": Decimal("5"), "currency": "XYZ"}], "SEK", lambda *a: None
        )


# ── what fetch_expenses hands to the logic modules ───────────────────────
def test_fetch_expenses_returns_every_field_the_logic_modules_read(client, make_user):
    from app.api.expenses import fetch_expenses
    from app.db.database import SessionLocal

    uid, h = make_user()
    client.post("/api/expenses", json={"date": str(TODAY), "category": "Food", "amount": "10", "currency": "SEK"}, headers=h)
    db = SessionLocal()
    try:
        [row] = fetch_expenses(db, uid)
    finally:
        db.close()
    assert set(row) == {
        "id", "date", "category", "subcategory", "description", "amount", "quantity", "unit",
        "shop", "brand", "currency", "price_per_unit", "bill_total_only", "recurring_template_id", "group_id", "user_id",
    }
    assert row["bill_total_only"] is False  # a real bool, as the shop scorecard expects
    assert row["recurring_template_id"] is None  # typed by hand, so not committed (spending mix reads this)
