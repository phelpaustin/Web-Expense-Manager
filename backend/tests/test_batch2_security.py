"""Imports run off the event loop, Google-only account deletion, rate-limit tuning."""
import inspect
import io
import zipfile

import pytest

from app.api import auth, bills, expenses
from app.core.config import settings
from app.core.file_upload import ensure_xlsx_within_limits
from app.core.import_limits import MAX_XLSX_UNCOMPRESSED_BYTES
from app.db import models
from app.db.database import SessionLocal


# ── imports no longer block the event loop ───────────────────────────────
@pytest.mark.parametrize(
    "endpoint",
    [expenses.import_expenses, bills.bulk_upload_pending, bills.upload_pending, bills.upload_receipt],
)
def test_upload_endpoints_are_plain_functions_so_they_run_in_a_worker_thread(endpoint):
    assert not inspect.iscoroutinefunction(endpoint)


def _zip_declaring(size: int) -> bytes:
    """A tiny .xlsx-looking zip whose single entry expands to `size` bytes of zeros."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", b"\0" * size)
    return buffer.getvalue()


def test_xlsx_that_expands_hugely_is_rejected_without_unpacking():
    bomb = _zip_declaring(MAX_XLSX_UNCOMPRESSED_BYTES + 1)
    assert len(bomb) < 1024 * 1024
    with pytest.raises(ValueError, match="too large"):
        ensure_xlsx_within_limits(bomb)


def test_non_zip_xlsx_is_rejected():
    with pytest.raises(ValueError, match="Not a valid"):
        ensure_xlsx_within_limits(b"definitely not a zip")


def test_import_endpoint_answers_400_for_a_zip_bomb(client, make_user):
    _, h = make_user()
    bomb = _zip_declaring(MAX_XLSX_UNCOMPRESSED_BYTES + 1)
    r = client.post("/api/expenses/import", files={"file": ("big.xlsx", bomb)}, headers=h)
    assert r.status_code == 400
    assert "too large" in r.text


def test_bill_statement_endpoint_answers_400_for_a_zip_bomb(client, make_user):
    _, h = make_user()
    bomb = _zip_declaring(MAX_XLSX_UNCOMPRESSED_BYTES + 1)
    r = client.post("/api/pending-bills/bulk-upload", files={"file": ("big.xlsx", bomb)}, headers=h)
    assert r.status_code == 400


def test_csv_import_still_works(client, make_user):
    _, h = make_user()
    csv = b"Date,Category,PricePaid\n2026-01-05,Food,12.50\n"
    r = client.post("/api/expenses/import", files={"file": ("e.csv", csv)}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 1


def test_oversized_receipt_is_still_refused(client, make_user, monkeypatch):
    _, h = make_user()
    monkeypatch.setattr(bills, "_MAX_RECEIPT_BYTES", 100)
    r = client.post("/api/pending-bills/upload", files={"file": ("r.pdf", b"%PDF" + b"x" * 500)}, headers=h)
    assert r.status_code == 400
    assert "too large" in r.text


# ── deleting a Google-only account ───────────────────────────────────────
def _google_user(make_user, email):
    uid, h = make_user(email)  # make_user stores a password; Google users never learn theirs
    return uid, h


def _fake_google(monkeypatch, email):
    monkeypatch.setattr(auth, "_verify_google_credential", lambda credential: ({"email": email}, email))


def _exists(uid):
    db = SessionLocal()
    try:
        return db.get(models.User, uid) is not None
    finally:
        db.close()


def test_google_confirmation_deletes_the_matching_account(client, make_user, monkeypatch):
    uid, h = _google_user(make_user, "g-delete@example.com")
    _fake_google(monkeypatch, "g-delete@example.com")
    r = client.post("/api/auth/delete-account", json={"google_credential": "tok"}, headers=h)
    assert r.status_code == 204, r.text
    assert not _exists(uid)


def test_google_confirmation_for_another_email_is_refused(client, make_user, monkeypatch):
    uid, h = _google_user(make_user, "g-keep@example.com")
    _fake_google(monkeypatch, "someone-else@example.com")
    r = client.post("/api/auth/delete-account", json={"google_credential": "tok"}, headers=h)
    assert r.status_code == 400
    assert _exists(uid)


def test_delete_needs_a_password_or_a_google_credential(client, make_user):
    uid, h = make_user()
    r = client.post("/api/auth/delete-account", json={}, headers=h)
    assert r.status_code == 422
    assert _exists(uid)


def test_wrong_password_still_refused_and_right_password_still_works(client, make_user):
    uid, h = make_user()
    assert client.post("/api/auth/delete-account", json={"password": "wrong-password-123"}, headers=h).status_code == 400
    assert _exists(uid)
    assert client.post("/api/auth/delete-account", json={"password": "correct-horse-battery"}, headers=h).status_code == 204
    assert not _exists(uid)


# ── rate limits are per visitor and tunable ──────────────────────────────
def _login(client, ip, email="nobody@example.com"):
    return client.post(
        "/api/auth/login",
        data={"username": email, "password": "wrong-password-123"},
        headers={"X-Forwarded-For": ip},
    )


def test_login_limit_applies_per_visitor_not_per_proxy(client, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    monkeypatch.setattr(settings, "rate_limit_login", "3/minute")
    statuses = [_login(client, "198.51.100.10").status_code for _ in range(4)]
    assert statuses == [401, 401, 401, 429]
    # A different visitor behind the same proxy is unaffected.
    assert _login(client, "198.51.100.11").status_code == 401


def test_default_limits_are_stricter_than_before():
    assert settings.rate_limit_login == "5/minute;60/hour"
    assert settings.rate_limit_register == "5/hour;20/day"
