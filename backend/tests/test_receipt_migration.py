"""Moving existing receipts out of the database, and the schema change behind it."""
import datetime as dt
import os
import sqlite3
import tempfile

import pytest

from app.core import receipt_storage as rs
from app.db import models
from app.db.database import SessionLocal
from app.scripts import migrate_receipts as mig
from tests.test_migration_0015 import _alembic
from tests.test_receipt_storage import PDF, PDF2, FakeStore


def _legacy(uid, n, content=PDF):
    """Receipts as they were stored before: bytes in the database, no storage key."""
    db = SessionLocal()
    ids = []
    for i in range(n):
        b = models.PendingBill(user_id=uid, date=dt.date(2026, 10, 1), shop=f"S{i}", amount=1, currency="SEK", note="", status="pending")
        db.add(b)
        db.flush()
        r = models.Receipt(user_id=uid, pending_bill_id=b.id, filename=f"r{i}.pdf", content_type="application/pdf", data=content + bytes([i]))
        db.add(r)
        db.flush()
        ids.append((b.id, r.id))
    db.commit()
    db.close()
    return ids


def _receipt(rid):
    db = SessionLocal()
    try:
        r = db.get(models.Receipt, rid)
        return r.storage_key, r.data
    finally:
        db.close()


@pytest.fixture
def store(monkeypatch):
    s = FakeStore()
    monkeypatch.setattr(rs, "get_store", lambda: s)
    return s


def test_every_receipt_moves_and_stays_downloadable(client, make_user, store):
    uid, h = make_user()
    ids = _legacy(uid, 3)
    stats = mig.migrate(store, out=lambda *_: None)
    assert stats["failed"] == 0 and stats["remaining"] == 0 and stats["moved"] >= 3
    for i, (bill_id, rid) in enumerate(ids):
        key, data = _receipt(rid)
        assert data is None and key.startswith(f"{uid}/{bill_id}/") and store.objects[key][0] == PDF + bytes([i])
        r = client.get(f"/api/pending-bills/{bill_id}/receipt", headers=h)
        assert r.status_code == 200 and r.content == PDF + bytes([i])
        assert r.headers["content-type"] == "application/pdf"


def test_running_it_again_moves_nothing_more(client, make_user, store):
    uid, _ = make_user()
    _legacy(uid, 2)
    mig.migrate(store, out=lambda *_: None)
    count = len(store.objects)
    again = mig.migrate(store, out=lambda *_: None)
    assert again["moved"] == 0 and len(store.objects) == count


def test_dry_run_changes_nothing(client, make_user, store):
    uid, _ = make_user()
    [(_, rid)] = _legacy(uid, 1)
    stats = mig.migrate(store, dry_run=True, out=lambda *_: None)
    assert stats["moved"] >= 1 and stats["remaining"] >= 1
    assert _receipt(rid)[0] is None and _receipt(rid)[1] is not None and store.objects == {}


def test_keep_data_copies_and_leaves_the_database_bytes_until_purged(client, make_user, store):
    uid, _ = make_user()
    [(_, rid)] = _legacy(uid, 1)
    mig.migrate(store, keep_data=True, out=lambda *_: None)
    key, data = _receipt(rid)
    assert key in store.objects and data is not None
    assert mig.purge_copied(out=lambda *_: None) >= 1
    assert _receipt(rid) == (key, None)


def test_purge_never_touches_a_receipt_that_is_not_in_storage(client, make_user, store):
    uid, _ = make_user()
    [(_, rid)] = _legacy(uid, 1)
    mig.purge_copied(out=lambda *_: None)
    assert _receipt(rid)[1] is not None


def test_a_failed_upload_leaves_that_receipt_untouched_and_the_rest_move(client, make_user, store):
    uid, _ = make_user()
    ids = _legacy(uid, 3)
    real_put = store.put
    bad = {"n": 0}

    def flaky(key, data, ctype):
        if data.endswith(bytes([1])) and data.startswith(PDF):  # the second of our three
            bad["n"] += 1
            raise rs.ReceiptStorageError("boom")
        real_put(key, data, ctype)

    store.put = flaky
    stats = mig.migrate(store, out=lambda *_: None)
    assert stats["failed"] == 1 and bad["n"] == 1
    assert _receipt(ids[1][1])[0] is None and _receipt(ids[1][1])[1] is not None  # still safely in the DB
    assert _receipt(ids[0][1])[1] is None and _receipt(ids[2][1])[1] is None
    store.put = real_put
    assert mig.migrate(store, out=lambda *_: None)["failed"] == 0  # a later run finishes it
    assert _receipt(ids[1][1])[1] is None


def test_a_readback_mismatch_keeps_the_database_copy(client, make_user, store):
    uid, _ = make_user()
    [(_, rid)] = _legacy(uid, 1)
    store.get = lambda key: b"corrupted"
    stats = mig.migrate(store, out=lambda *_: None)
    assert stats["failed"] >= 1
    assert _receipt(rid)[0] is None and _receipt(rid)[1] is not None
    assert store.objects == {}  # the bad upload was removed


def test_limit_stops_early(client, make_user, store):
    uid, _ = make_user()
    ids = _legacy(uid, 3)
    stats = mig.migrate(store, limit=1, out=lambda *_: None)
    assert stats["moved"] == 1 and stats["remaining"] >= 2


def test_the_check_command_round_trips_and_reports_problems(store, capsys):
    assert mig.check(store) is True and store.objects == {}
    store.fail_put = True
    assert mig.check(store) is False
    assert "FAILED" in capsys.readouterr().out


def test_main_explains_when_storage_is_not_configured(monkeypatch, capsys):
    monkeypatch.setattr(rs, "get_store", lambda: None)
    assert mig.main(["--dry-run"]) == 2
    assert "SUPABASE_URL" in capsys.readouterr().out


# ── schema ──────────────────────────────────────────────────────────────
def test_0024_adds_the_column_makes_data_optional_and_downgrades_safely():
    path = os.path.join(tempfile.mkdtemp(), "r.db")
    assert _alembic(path, "upgrade", "0023_normalise_categories").returncode == 0
    con = sqlite3.connect(path)
    # the pre-0024 shape: no storage_key, data NOT NULL
    con.execute("DROP TABLE receipts")
    con.execute("CREATE TABLE receipts (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, pending_bill_id INTEGER NOT NULL, "
                "filename VARCHAR NOT NULL, content_type VARCHAR NOT NULL, data BLOB NOT NULL)")
    con.execute("INSERT INTO receipts (user_id, pending_bill_id, filename, content_type, data) VALUES (1, 1, 'a.pdf', 'application/pdf', x'25504446')")
    con.commit()
    con.close()

    assert _alembic(path, "upgrade", "head").returncode == 0
    con = sqlite3.connect(path)
    cols = {r[1]: r for r in con.execute("PRAGMA table_info(receipts)")}
    assert "storage_key" in cols and cols["data"][3] == 0  # data is nullable now
    assert con.execute("SELECT data FROM receipts").fetchone() == (b"%PDF",)  # existing bytes untouched
    con.execute("INSERT INTO receipts (user_id, pending_bill_id, filename, content_type, data, storage_key) VALUES (1, 2, 'b.pdf', 'application/pdf', NULL, 'k')")
    con.commit()
    con.close()

    # a receipt that lives only in storage blocks the downgrade, loudly
    r = _alembic(path, "downgrade", "0023_normalise_categories")
    assert r.returncode != 0 and "object storage" in r.stderr
    con = sqlite3.connect(path)
    con.execute("DELETE FROM receipts WHERE data IS NULL")
    con.commit()
    con.close()
    assert _alembic(path, "downgrade", "0023_normalise_categories").returncode == 0
    assert _alembic(path, "upgrade", "head").returncode == 0
    assert _alembic(path, "upgrade", "head").returncode == 0  # idempotent
