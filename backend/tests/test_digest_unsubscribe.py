"""Release 12: unsubscribe from the budget-alert digest."""
from datetime import date

import pytest

import app.api.alerts as alerts
from app.core.config import settings
from app.core.security import create_access_token, create_reset_token, create_unsubscribe_token

TODAY = date.today().isoformat()


@pytest.fixture
def sent(monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "s3cret")
    out = []

    def fake(to, subject, body, headers=None):
        out.append({"to": to, "body": body, "headers": headers or {}})
        return True

    monkeypatch.setattr(alerts, "send_email", fake)
    return out


def _over_budget(client, h):
    client.put("/api/budgets", json={"category": "__total_monthly__", "amount": "1"}, headers=h)
    r = client.post("/api/expenses", json={"date": TODAY, "category": "Food", "amount": "999", "currency": "SEK"}, headers=h)
    assert r.status_code in (200, 201), r.text


def _digest(client):
    r = client.post("/api/alerts/send-digest", headers={"X-Cron-Secret": "s3cret"})
    assert r.status_code == 200
    return r.json()


def _email(client, h):
    return client.get("/api/auth/me", headers=h).json()["email"]


    return jwt.decode(h["Authorization"].split()[1], options={"verify_signature": False})["sub"]


def test_digest_contains_unsubscribe_link_and_header(client, make_user, sent):
    uid, h = make_user()
    _over_budget(client, h)
    _digest(client)
    mine = [m for m in sent if m["to"] == _email(client, h)]
    assert len(mine) == 1
    assert "/unsubscribe?token=" in mine[0]["body"]
    assert mine[0]["headers"]["List-Unsubscribe"].startswith("<") and "/unsubscribe?token=" in mine[0]["headers"]["List-Unsubscribe"]


def test_unsubscribe_link_stops_digest(client, make_user, sent):
    uid, h = make_user()
    _over_budget(client, h)
    token = create_unsubscribe_token(str(uid))
    r = client.post("/api/alerts/unsubscribe", json={"token": token})  # no login needed
    assert r.status_code == 200
    _digest(client)
    assert not [m for m in sent if m["to"] == _email(client, h)]
    # repeating is harmless
    assert client.post("/api/alerts/unsubscribe", json={"token": token}).status_code == 200
    assert client.get("/api/options", headers=h).json()["alert_digest_enabled"] is False


@pytest.mark.parametrize("bad", ["", "garbage", None])
def test_invalid_token_rejected(client, bad):
    r = client.post("/api/alerts/unsubscribe", json={"token": bad if bad is not None else 5})
    assert r.status_code in (400, 422)


def test_other_token_types_cannot_unsubscribe(client, make_user):
    uid, h = make_user()
    for tok in (create_reset_token(str(uid), 0), h["Authorization"].split()[1]):
        assert client.post("/api/alerts/unsubscribe", json={"token": tok}).status_code == 400
    assert client.get("/api/options", headers=h).json()["alert_digest_enabled"] is True


def test_token_for_missing_user_rejected(client):
    assert client.post("/api/alerts/unsubscribe", json={"token": create_unsubscribe_token("99999999")}).status_code == 400


def test_toggle_in_settings_and_resubscribe(client, make_user, sent):
    uid, h = make_user()
    _over_budget(client, h)
    assert client.get("/api/options", headers=h).json()["alert_digest_enabled"] is True
    r = client.post("/api/options/alert-digest", json={"enabled": False}, headers=h)
    assert r.status_code == 200 and r.json()["alert_digest_enabled"] is False
    _digest(client)
    assert not [m for m in sent if m["to"] == _email(client, h)]
    client.post("/api/options/alert-digest", json={"enabled": True}, headers=h)
    _digest(client)
    assert [m for m in sent if m["to"] == _email(client, h)]


def test_migration_0021_adds_column_defaulting_on():
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0021_alert_digest_enabled.py"
    spec = importlib.util.spec_from_file_location("mig0021", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    eng = sa.create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE user_options (id integer primary key, user_id integer)"))
        c.execute(sa.text("INSERT INTO user_options (user_id) VALUES (1)"))
        with Operations.context(MigrationContext.configure(c)):
            mig.upgrade()
            mig.upgrade()  # idempotent
        assert c.execute(sa.text("SELECT alert_digest_enabled FROM user_options")).scalar() in (1, True)
