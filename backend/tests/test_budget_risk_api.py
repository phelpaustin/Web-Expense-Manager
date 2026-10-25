import datetime as dt

import pytest

from app.logic import budget_risk as br

URL = "/api/budgets/risk"
TOTAL = "__total_monthly__"


def month_back(n):
    t = dt.date.today()
    i = t.year * 12 + (t.month - 1) - n
    return i // 12, i % 12 + 1


def spend(client, h, category, amount, when, **extra):
    r = client.post("/api/expenses", json={"date": when, "category": category, "description": category, "amount": str(amount),
                                           "currency": "SEK", **extra}, headers=h)
    assert r.status_code == 201, r.text


def history(client, h, category, amounts, day=28):
    """One purchase on the `day`th of each earlier month, newest month last."""
    for back, amount in zip(range(len(amounts), 0, -1), amounts):
        y, m = month_back(back)
        spend(client, h, category, amount, f"{y:04d}-{m:02d}-{day:02d}")


def budget(client, h, category, amount):
    assert client.put("/api/budgets", json={"category": category, "amount": str(amount)}, headers=h).status_code == 200


def risk(client, h, **params):
    r = client.get(URL, params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def by_name(result):
    return {i["category"]: i for i in result["items"]}


@pytest.fixture
def on_the_10th(monkeypatch):
    """Judge risk as of the 10th of the real current month, so the answer doesn't depend on the day the tests run."""
    real = br.budget_risk
    fixed = dt.date.today().replace(day=10)
    monkeypatch.setattr(br, "budget_risk", lambda expenses, categories, period, today=None: real(expenses, categories, period, today=fixed))


# --- the endpoint --------------------------------------------------------------------------------

def test_it_needs_a_login_and_starts_empty(client, make_user):
    _, h = make_user()

    assert client.get(URL).status_code == 401
    assert risk(client, h) == {"today": dt.date.today().isoformat(), "has_budgets": False, "items": [], "min_periods": 4, "alert_threshold": 75.0}


def test_a_category_budget_gets_a_chance_and_the_evidence_for_it(client, make_user, on_the_10th):
    _, h = make_user()
    history(client, h, "Groceries", [500] * 6)                    # 500 spent after the 10th, every earlier month
    budget(client, h, "Groceries", 1000)
    spend(client, h, "Groceries", 600, dt.date.today().isoformat())          # 400 left this month

    g = by_name(risk(client, h))["Groceries"]

    assert g["available"] and (g["samples"], g["exceeded"]) == (6, 6)
    assert g["probability"] == pytest.approx(6.5 / 7 * 100, abs=0.05) and g["level"] == "very_likely"
    assert float(g["remaining"]) == 400.0 and float(g["typical_remaining"]) == 500.0 and g["period"] == "Monthly"


def test_the_numbers_match_the_budget_bars(client, make_user, on_the_10th):
    _, h = make_user()
    history(client, h, "Groceries", [100] * 5)
    budget(client, h, "Groceries", 800)
    spend(client, h, "Groceries", 250, dt.date.today().isoformat())

    g = by_name(risk(client, h))["Groceries"]
    bar = next(s for s in client.get("/api/budgets/status", headers=h).json() if s["category"] == "Groceries")

    assert (g["limit"], g["spent"], g["remaining"], g["pct"]) == (bar["budget"], bar["spent"], bar["remaining"], bar["pct"])


def test_a_budget_that_is_already_blown_is_certain(client, make_user, on_the_10th):
    _, h = make_user()
    budget(client, h, "Fun", 100)
    spend(client, h, "Fun", 160, dt.date.today().isoformat())

    f = by_name(risk(client, h))["Fun"]

    assert f["available"] and f["probability"] == 100.0 and f["level"] == "over"


def test_a_category_without_enough_history_says_so_instead_of_guessing(client, make_user, on_the_10th):
    _, h = make_user()
    history(client, h, "Gifts", [50, 60, 70])                      # three earlier months: one short
    budget(client, h, "Gifts", 500)

    g = by_name(risk(client, h))["Gifts"]

    assert (g["available"], g["reason"], g["samples"], g["probability"]) == (False, "not_enough_history", 3, None)


def test_the_total_budget_uses_its_period_status(client, make_user):
    _, h = make_user()
    budget(client, h, TOTAL, 100)
    spend(client, h, "Food", 160, dt.date.today().isoformat())

    t = by_name(risk(client, h))["Total"]
    ps = client.get("/api/budgets/period-status", headers=h).json()

    assert t["is_total"] and t["level"] == "over" and t["probability"] == 100.0
    assert (t["limit"], t["spent"], t["remaining"]) == (ps["effective"], ps["spent"], ps["remaining"])


def test_scope_narrows_it_like_the_other_dashboard_figures(client, make_user, on_the_10th):
    _, h = make_user()
    gid = client.post("/api/groups", json={"name": "Home"}, headers=h).json()["id"]
    budget(client, h, "Shared", 100)
    spend(client, h, "Shared", 150, dt.date.today().isoformat(), group_id=gid)

    everything = by_name(risk(client, h))["Shared"]
    personal = by_name(risk(client, h, scope="personal"))["Shared"]

    assert float(everything["spent"]) == 150.0 and float(personal["spent"]) == 0.0


def test_it_only_ever_describes_your_own_budgets(client, make_user, on_the_10th):
    _, alice = make_user()
    _, bob = make_user()
    budget(client, alice, "Groceries", 500)

    assert risk(client, bob)["items"] == [] and risk(client, alice)["has_budgets"] is True


# --- alerts and the dashboard ---------------------------------------------------------------------

def alert_ids(client, h):
    r = client.get("/api/alerts", headers=h)
    assert r.status_code == 200, r.text
    return {a["id"]: a for a in r.json()}


def test_a_likely_overrun_becomes_an_alert(client, make_user, on_the_10th):
    _, h = make_user()
    history(client, h, "Groceries", [500] * 6)
    budget(client, h, "Groceries", 1000)
    spend(client, h, "Groceries", 600, dt.date.today().isoformat())

    alert = alert_ids(client, h)["risk:Groceries"]

    assert alert["severity"] == "warning" and alert["category"] == "Groceries"
    assert alert["message"].startswith("Groceries budget: about 93% chance of going over this month (400.00 left; in 6 of the last 6 months")


def test_an_unlikely_overrun_does_not(client, make_user, on_the_10th):
    _, h = make_user()
    history(client, h, "Groceries", [20] * 6)
    budget(client, h, "Groceries", 1000)
    spend(client, h, "Groceries", 600, dt.date.today().isoformat())              # 400 left; at most 20 more is typical

    assert "risk:Groceries" not in alert_ids(client, h)


def test_without_enough_history_there_is_no_risk_alert(client, make_user, on_the_10th):
    _, h = make_user()
    history(client, h, "Groceries", [500] * 3)
    budget(client, h, "Groceries", 1000)
    spend(client, h, "Groceries", 600, dt.date.today().isoformat())

    assert not any(i.startswith("risk:") for i in alert_ids(client, h))


def test_the_dashboard_carries_the_same_section(client, make_user, on_the_10th):
    _, h = make_user()
    history(client, h, "Groceries", [500] * 5)
    budget(client, h, "Groceries", 1000)

    dash = client.get("/api/dashboard", headers=h).json()

    assert dash["budget_risk"] == risk(client, h) and dash["budget_risk"]["items"][0]["category"] == "Groceries"
