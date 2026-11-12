"""ALLOW_REGISTRATION=false closes sign-up (register, first-time Google) but keeps existing accounts working."""
import pytest

from app.api import auth as auth_api
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db import models
from app.db.database import SessionLocal


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    limiter.reset()
    monkeypatch.setattr(auth_api, "send_email", lambda *a, **k: True)
    yield
    limiter.reset()


def _count(email):
    with SessionLocal() as db:
        return db.query(models.User).filter(models.User.email == email).count()


def test_register_open_by_default(client):
    assert settings.allow_registration is True
    assert client.post("/api/auth/register", json={"email": "new1@example.com"}).status_code == 201


def test_register_closed(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_registration", False)
    r = client.post("/api/auth/register", json={"email": "new2@example.com"})
    assert r.status_code == 403
    assert _count("new2@example.com") == 0


def test_closed_answer_is_the_same_for_known_and_unknown_addresses(client, make_user, monkeypatch):
    make_user(email="known@example.com")
    monkeypatch.setattr(settings, "allow_registration", False)
    a = client.post("/api/auth/register", json={"email": "known@example.com"})
    b = client.post("/api/auth/register", json={"email": "unknown@example.com"})
    assert (a.status_code, a.json()) == (b.status_code, b.json())


def test_google_first_sign_in_refused_when_closed(client, monkeypatch):
    monkeypatch.setattr(auth_api, "_verify_google_credential", lambda c: ({"name": "G"}, "g@example.com"))
    monkeypatch.setattr(settings, "allow_registration", False)
    assert client.post("/api/auth/google", json={"credential": "x"}).status_code == 403
    assert _count("g@example.com") == 0


def test_google_existing_account_still_signs_in_when_closed(client, make_user, monkeypatch):
    make_user(email="g2@example.com")
    monkeypatch.setattr(auth_api, "_verify_google_credential", lambda c: ({"name": "G"}, "g2@example.com"))
    monkeypatch.setattr(settings, "allow_registration", False)
    assert client.post("/api/auth/google", json={"credential": "x"}).status_code == 200
