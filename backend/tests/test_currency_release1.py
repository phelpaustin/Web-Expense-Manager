"""Release 1: one unconvertible currency must not break the app."""
import datetime

from app.db import models
from app.db.database import SessionLocal

TODAY = datetime.date.today().isoformat()


def _expense(client, headers, currency, amount="10"):
    return client.post(
        "/api/expenses",
        json={"date": TODAY, "category": "Food", "amount": amount, "currency": currency},
        headers=headers,
    )


def _insert_raw_expense(user_id, currency, amount=5):
    """Simulate a row already in the DB with a currency we can't convert."""
    db = SessionLocal()
    db.add(models.Expense(user_id=user_id, date=datetime.date.today(), category="Food",
                          amount=amount, currency=currency))
    db.commit()
    db.close()


# ── write-time validation ────────────────────────────────────────────────
def test_unsupported_currency_rejected_on_create(client, make_user):
    _, h = make_user()
    assert _expense(client, h, "XXX").status_code == 422
    assert _expense(client, h, "XAU").status_code == 422
    assert _expense(client, h, "EUR").status_code == 201


def test_unsupported_currency_rejected_on_update(client, make_user):
    _, h = make_user()
    exp = _expense(client, h, "SEK").json()
    r = client.put(f"/api/expenses/{exp['id']}", json={"currency": "XXX"}, headers=h)
    assert r.status_code == 422


def test_unsupported_currency_rejected_in_bulk(client, make_user):
    _, h = make_user()
    items = [{"date": TODAY, "category": "Food", "amount": "1", "currency": c} for c in ("SEK", "XXX")]
    assert client.post("/api/expenses/bulk", json={"items": items}, headers=h).status_code == 422


def test_base_currency_must_be_convertible(client, make_user):
    _, h = make_user()
    assert client.post("/api/options/base-currency", json={"currency": "XXX"}, headers=h).status_code == 422
    assert client.post("/api/options/base-currency", json={"currency": "eur"}, headers=h).status_code == 200


def test_trip_currency_must_be_convertible(client, make_user):
    _, h = make_user()
    assert client.post("/api/trips", json={"name": "T", "currency": "XXX"}, headers=h).status_code == 422
    assert client.post("/api/trips", json={"name": "T", "currency": "USD"}, headers=h).status_code == 201


def test_import_reports_unsupported_currency_per_row(client, make_user):
    _, h = make_user()
    csv = f"Date,Category,Amount,Currency\n{TODAY},Food,5,SEK\n{TODAY},Food,6,XXX\n".encode()
    r = client.post("/api/expenses/import", files={"file": ("x.csv", csv, "text/csv")}, headers=h)
    body = r.json()
    assert r.status_code == 200
    assert body["added"] == 1 and body["skipped"] == 1
    assert "XXX" in body["skipped_rows"][0]["reason"]


# ── read path survives an already-stored bad row ─────────────────────────
def test_aggregates_survive_unconvertible_row(client, make_user):
    uid, h = make_user()
    assert _expense(client, h, "SEK", "100").status_code == 201
    _insert_raw_expense(uid, "XXX")

    s = client.get("/api/expenses/summary", headers=h)
    assert s.status_code == 200
    body = s.json()
    assert body["unconverted_count"] == 1
    assert body["count"] == 1  # only the convertible expense is aggregated

    for path in ["/api/analytics/trends", "/api/analytics/categories", "/api/budgets/status",
                 "/api/budgets/period-status", "/api/metrics", "/api/alerts", "/api/bills-ledger"]:
        assert client.get(path, headers=h).status_code == 200, path

    # the expense list never depended on FX and still shows every row
    assert client.get("/api/expenses", headers=h).json()["total"] == 2


def test_bad_row_in_shared_space_does_not_break_other_member(client, make_user):
    owner_id, h_owner = make_user()
    member_id, h_member = make_user()
    g = client.post("/api/groups", json={"name": "House", "space_type": "household"}, headers=h_owner).json()
    db = SessionLocal()
    db.add(models.GroupMember(group_id=g["id"], user_id=member_id, role="editor"))
    db.add(models.Expense(user_id=member_id, group_id=g["id"], date=datetime.date.today(),
                          category="Food", amount=1, currency="XXX"))
    db.commit()
    db.close()
    assert client.get("/api/expenses/summary", headers=h_owner).status_code == 200
    assert client.get("/api/metrics", headers=h_owner).status_code == 200


# ── digest ───────────────────────────────────────────────────────────────
def test_digest_continues_past_failing_user(client, make_user, monkeypatch):
    import app.api.alerts as alerts
    from app.core.config import settings

    monkeypatch.setattr(settings, "cron_secret", "s3cret")
    uid_bad, _ = make_user()
    uid_ok, h_ok = make_user()
    sent = []
    real = alerts._alerts_for_user

    def flaky(db, user_id):
        if user_id == uid_bad:
            raise RuntimeError("boom")
        return real(db, user_id)

    monkeypatch.setattr(alerts, "_alerts_for_user", flaky)
    monkeypatch.setattr(alerts, "send_email", lambda to, subj, body: sent.append(to) or True)

    client.put("/api/budgets", json={"category": "__total_monthly__", "amount": "1"}, headers=h_ok)
    client.post("/api/expenses", json={"date": TODAY, "category": "Food", "amount": "999", "currency": "SEK"}, headers=h_ok)

    r = client.post("/api/alerts/send-digest", headers={"X-Cron-Secret": "s3cret"})
    assert r.status_code == 200
    body = r.json()
    assert body["users_failed"] >= 1
    assert body["users_emailed"] >= 1  # the healthy user still got their email


def test_digest_rejects_wrong_secret(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "cron_secret", "s3cret")
    assert client.post("/api/alerts/send-digest", headers={"X-Cron-Secret": "nope"}).status_code == 403
    assert client.post("/api/alerts/send-digest").status_code == 403


# ── fx module ────────────────────────────────────────────────────────────
def test_fx_negative_cache_avoids_repeated_timeouts(monkeypatch):
    from app.core import fx
    calls = []
    monkeypatch.setattr(fx, "_fetch_rates", lambda base: calls.append(base) or None)
    fx._cache.clear()
    fx._last_failure.clear()
    assert fx.get_rates("JPY") is None
    assert fx.get_rates("JPY") is None
    assert fx.get_rates("JPY") is None
    assert len(calls) == 1  # backed off after the first failure


def test_fallback_list_used_when_rates_unavailable(monkeypatch):
    from app.core import fx
    monkeypatch.undo()  # drop the autouse fake so the real function runs
    monkeypatch.setattr(fx, "get_rates", lambda base: None)
    assert "SEK" in fx.supported_currencies()
    assert "XXX" not in fx.supported_currencies()
    assert fx.normalize_convertible_currency("sek") == "SEK"
