"""Sign-in history: successes and failed password attempts are recorded for existing accounts."""
import datetime as dt

import pytest

from app.api import auth
from app.core.rate_limit import limiter
from app.core.security import create_access_token, hash_password
from app.db import models
from app.db.database import SessionLocal
from app.logic import sign_ins

MAC_CHROME = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
IPHONE_SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"


@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.reset()
    yield
    limiter.reset()


_n = [0]


def _make(email=None):
    _n[0] += 1
    email = email or f"si{_n[0]}@example.com"
    db = SessionLocal()
    u = models.User(email=email, hashed_password=hash_password("correct-horse-battery"), name="n", email_verified=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    uid, sv = u.id, u.session_version
    db.close()
    return uid, {"Authorization": "Bearer " + create_access_token(str(uid), sv)}, email


def _login(client, email, password, ua=MAC_CHROME):
    return client.post("/api/auth/login", data={"username": email, "password": password}, headers={"User-Agent": ua})


def _events(h, client):
    r = client.get("/api/auth/sign-ins", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_successful_login_is_recorded_with_device_and_ip(client):
    _uid, h, em = _make()
    assert _login(client, em, "correct-horse-battery").status_code == 200
    data = _events(h, client)
    [e] = data["events"]
    assert e["success"] is True and e["method"] == "password" and e["device"] == "Chrome on Mac" and e["ip"]
    assert data["failed_since_last_success"] == 0


def test_a_wrong_password_is_recorded_as_a_failure_and_counted_until_the_next_success(client):
    _uid, h, em = _make()
    for _ in range(2):
        assert _login(client, em, "nope-nope-nope-1", IPHONE_SAFARI).status_code == 401
    data = _events(h, client)
    assert [e["success"] for e in data["events"]] == [False, False]
    assert data["events"][0]["device"] == "Safari on iPhone" and data["failed_since_last_success"] == 2
    assert _login(client, em, "correct-horse-battery").status_code == 200
    assert _events(h, client)["failed_since_last_success"] == 0


def test_unknown_addresses_and_unverified_accounts_leave_no_history(client):
    _, _h, _e = _make()  # an unrelated account with no history
    assert _login(client, "ghost@example.com", "whatever-123456").status_code == 401
    db = SessionLocal()
    before = db.query(models.SignInEvent).count()
    u = models.User(email="unv@example.com", hashed_password=hash_password("correct-horse-battery"), name="n", email_verified=False)
    db.add(u)
    db.commit()
    db.close()
    assert _login(client, "unv@example.com", "correct-horse-battery").status_code == 403
    db = SessionLocal()
    assert db.query(models.SignInEvent).count() == before
    db.close()


def test_each_account_sees_only_its_own_history(client):
    _a, ha, ea = _make()
    _b, hb, _eb = _make()
    _login(client, ea, "correct-horse-battery")
    assert len(_events(ha, client)["events"]) == 1
    assert _events(hb, client)["events"] == []


def test_google_sign_in_is_recorded(client, monkeypatch):
    _uid, h, em = _make()
    monkeypatch.setattr(auth, "_verify_google_credential", lambda credential: ({"email": em, "name": "G"}, em))
    assert client.post("/api/auth/google", json={"credential": "tok"}).status_code == 200
    [e] = _events(h, client)["events"]
    assert e["method"] == "google" and e["success"] is True


def test_the_history_needs_a_login(client):
    assert client.get("/api/auth/sign-ins").status_code == 401


def test_old_events_and_floods_are_pruned(client):
    uid, h, _em = _make()
    db = SessionLocal()
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=sign_ins.KEEP_DAYS + 5)
    db.add(models.SignInEvent(user_id=uid, at=old, method="password", success=True, ip="1.1.1.1", user_agent=""))
    db.commit()
    db.close()
    sign_ins.record_sign_in(uid, "password", False, "2.2.2.2", "")
    db = SessionLocal()
    assert [e.ip for e in db.query(models.SignInEvent).filter_by(user_id=uid)] == ["2.2.2.2"]
    db.close()

    sign_ins.KEEP_ROWS, keep = 5, sign_ins.KEEP_ROWS
    try:
        for i in range(12):
            sign_ins.record_sign_in(uid, "password", False, f"9.9.9.{i}", "")
    finally:
        sign_ins.KEEP_ROWS = keep
    db = SessionLocal()
    assert db.query(models.SignInEvent).filter_by(user_id=uid).count() <= 6
    db.close()


def test_deleting_the_account_removes_its_history(client):
    uid, h, em = _make()
    _login(client, em, "correct-horse-battery")
    assert client.post("/api/auth/delete-account", json={"password": "correct-horse-battery"}, headers=h).status_code == 204
    db = SessionLocal()
    assert db.query(models.SignInEvent).filter_by(user_id=uid).count() == 0
    db.close()


def test_long_user_agents_and_missing_ones_are_stored_safely(client):
    uid, h, _em = _make()
    sign_ins.record_sign_in(uid, "password", True, "x" * 200, "y" * 5000)
    sign_ins.record_sign_in(uid, "password", True, "1.2.3.4", "")
    db = SessionLocal()
    rows = db.query(models.SignInEvent).filter_by(user_id=uid).order_by(models.SignInEvent.id).all()
    assert len(rows[0].ip) == 64 and len(rows[0].user_agent) == 300
    db.close()
    assert [e["device"] for e in _events(h, client)["events"]][0] == ""


def test_device_names():
    assert sign_ins.device_name(MAC_CHROME) == "Chrome on Mac"
    assert sign_ins.device_name(IPHONE_SAFARI) == "Safari on iPhone"
    assert sign_ins.device_name("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/131.0") == "Firefox on Windows"
    assert sign_ins.device_name("Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36 EdgA/130") == "Edge on Android"
    assert sign_ins.device_name("curl/8.4.0") == "Script"
    assert sign_ins.device_name("") == ""
