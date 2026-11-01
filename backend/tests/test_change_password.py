"""Changing the password signs out other devices but keeps the one that changed it signed in."""
import pytest

from app.core.rate_limit import limiter
from app.core.security import create_access_token, hash_password
from app.db import models
from app.db.database import SessionLocal


@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.reset()
    yield
    limiter.reset()


def _user(email):
    db = SessionLocal()
    try:
        u = models.User(email=email, hashed_password=hash_password("correct-horse-battery"), name="N", email_verified=True)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id, create_access_token(str(u.id), u.session_version)
    finally:
        db.close()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_change_password_returns_a_token_that_still_works_and_retires_the_old_one(client):
    _, old = _user("changer@example.com")
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "correct-horse-battery", "new_password": "a-brand-new-passphrase"},
        headers=_auth(old),
    )
    assert r.status_code == 200
    fresh = r.json()["access_token"]
    assert client.get("/api/auth/me", headers=_auth(fresh)).status_code == 200  # this device stays signed in
    assert client.get("/api/auth/me", headers=_auth(old)).status_code == 401  # other devices are signed out


def test_wrong_current_password_changes_nothing(client):
    _, token = _user("changer2@example.com")
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "not-the-password-1", "new_password": "a-brand-new-passphrase"},
        headers=_auth(token),
    )
    assert r.status_code == 400
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 200


def test_unknown_email_login_still_answers_401(client):
    r = client.post("/api/auth/login", data={"username": "nobody@example.com", "password": "whatever-password-1"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect email or password"
