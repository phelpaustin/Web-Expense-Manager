import datetime as dt

from app.api.alerts import _alerts_for_user
from app.db.database import SessionLocal

URL = "/api/analytics/price-trends/rises"


def day(n):
    return (dt.date.today() - dt.timedelta(days=n)).isoformat()


def buy(client, h, item, price, when, shop="ICA", unit="Litre", category="Food"):
    r = client.post("/api/expenses", json={"date": when, "category": category, "description": item, "amount": str(price), "quantity": 1,
                                           "unit": unit, "shop": shop, "currency": "SEK"}, headers=h)
    assert r.status_code in (200, 201), r.text


def milk(client, h, now=13):
    buy(client, h, "Milk", 10, day(80)); buy(client, h, "Milk", 10, day(50)); buy(client, h, "Milk", now, day(3))


def get(client, h, **params):
    r = client.get(URL, params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def uid(client, h):
    return client.get("/api/auth/me", headers=h).json()["id"]


def test_a_rise_is_found(client, make_user):
    _, h = make_user()
    milk(client, h)
    r = get(client, h)
    [m] = r["items"]
    assert m["item"] == "Milk" and m["shop"] == "ICA" and m["rise_pct"] == 30.0 and float(m["usual_price"]) == 10.0
    assert r["currency"] == "SEK" and r["recent_days"] == 30 and r["total_found"] == 1


def test_the_price_is_per_unit(client, make_user):
    _, h = make_user()
    for n, p in ((80, 20), (50, 20)):
        r = client.post("/api/expenses", json={"date": day(n), "category": "Food", "description": "Milk", "amount": str(p), "quantity": 2,
                                               "unit": "Litre", "shop": "ICA", "currency": "SEK"}, headers=h)
        assert r.status_code in (200, 201)
    buy(client, h, "Milk", 13, day(3))                       # 13 per litre against 10 per litre
    assert get(client, h)["items"][0]["rise_pct"] == 30.0


def test_the_options_and_bad_input(client, make_user):
    _, h = make_user()
    milk(client, h, now=11)                                  # 10%: exactly the default threshold
    assert len(get(client, h)["items"]) == 1
    assert get(client, h, min_rise_pct=20)["items"] == []
    assert get(client, h, recent_days=1)["items"] == []      # the purchase was 3 days ago
    for bad in ({"recent_days": 0}, {"recent_days": 367}, {"min_rise_pct": -1}, {"top": 0}, {"top": 51}, {"top": "x"}):
        assert client.get(URL, params=bad, headers=h).status_code == 422


def test_shop_merges_are_followed(client, make_user):
    _, h = make_user()
    buy(client, h, "Milk", 10, day(80), shop="ICA Maxi"); buy(client, h, "Milk", 10, day(50), shop="ICA"); buy(client, h, "Milk", 13, day(3), shop="ICA")
    assert get(client, h)["items"] == []                    # different shops until merged
    assert client.post("/api/aliases/merge", json={"kind": "shop", "names": ["ICA Maxi"], "canonical": "ICA"}, headers=h).status_code in (200, 201)
    assert get(client, h)["items"][0]["earlier_purchases"] == 2


def test_needs_a_login(client):
    assert client.get(URL).status_code in (401, 403)


def test_each_person_sees_only_their_own_purchases(client, make_user):
    _, a = make_user(); _, b = make_user()
    milk(client, a)
    buy(client, a, "Secret item", 10, day(80), shop="Hidden"); buy(client, a, "Secret item", 10, day(50), shop="Hidden"); buy(client, a, "Secret item", 50, day(3), shop="Hidden")
    seen = get(client, b)
    assert seen["items"] == [] and seen["checked"] == 0
    assert "Secret" not in str(seen) and "Hidden" not in str(seen)


# --- the bell, the dashboard and the digest ----------------------------------------------------

def test_the_bell_shows_price_rises(client, make_user):
    _, h = make_user()
    milk(client, h)
    alerts = client.get("/api/alerts", headers=h).json()
    assert [a["message"] for a in alerts if a["category"] == "Prices"] == ["Milk at ICA now costs 13.00 per Litre, 30% more than your usual 10.00"]


def test_the_dashboard_carries_them_too(client, make_user):
    _, h = make_user()
    milk(client, h)
    alerts = client.get("/api/dashboard", headers=h).json()["alerts"]
    assert any(a["category"] == "Prices" for a in alerts)


def test_the_daily_digest_email_stays_budget_only(client, make_user):
    _, h = make_user()
    milk(client, h)
    with SessionLocal() as db:
        assert [a for a in _alerts_for_user(db, uid(client, h)) if a["category"] == "Prices"] == []
        assert any(a["category"] == "Prices" for a in _alerts_for_user(db, uid(client, h), include_prices=True))


def test_price_alerts_do_not_hide_budget_alerts(client, make_user):
    _, h = make_user()
    milk(client, h)
    buy(client, h, "Bread", 100, day(0), category="Food")                       # spent today, so inside this month
    assert client.put("/api/budgets", json={"category": "Food", "amount": "50"}, headers=h).status_code == 200
    alerts = client.get("/api/alerts", headers=h).json()
    assert alerts[0]["severity"] == "critical" and alerts[0]["category"] != "Prices"   # the exceeded budget comes first
    assert any(a["category"] == "Prices" for a in alerts)
    ranks = [{"critical": 3, "warning": 2, "caution": 1, "info": 0}[a["severity"]] for a in alerts]
    assert ranks == sorted(ranks, reverse=True)
