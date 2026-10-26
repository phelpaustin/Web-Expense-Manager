"""Migration 0028: the old manual ledger table is dropped only when it is empty."""
import os
import sqlite3
import tempfile

from tests.test_migration_0015 import _alembic


def _tables(path):
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        con.close()


def _db_at_0027():
    path = os.path.join(tempfile.mkdtemp(), "m28.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    assert _alembic(path, "downgrade", "0027_import_profiles").returncode == 0  # the shape before 0028
    return path


def test_a_fresh_database_has_no_manual_bills_table():
    path = os.path.join(tempfile.mkdtemp(), "fresh.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    assert "manual_bills" not in _tables(path)


def test_the_downgrade_brings_the_table_back_and_the_upgrade_drops_it_when_empty():
    path = _db_at_0027()
    assert "manual_bills" in _tables(path)
    con = sqlite3.connect(path)
    cols = {r[1] for r in con.execute("PRAGMA table_info(manual_bills)")}
    con.close()
    assert cols == {"id", "user_id", "date", "shop", "amount", "note", "currency"}

    assert _alembic(path, "upgrade", "head").returncode == 0
    assert "manual_bills" not in _tables(path)
    assert _alembic(path, "upgrade", "head").returncode == 0  # idempotent


def test_the_table_is_kept_with_its_rows_when_anything_is_left_in_it():
    path = _db_at_0027()
    con = sqlite3.connect(path)
    con.execute("INSERT INTO users (id, email, hashed_password, name) VALUES (1, 'a@x.com', 'h', 'a')")
    con.execute("INSERT INTO manual_bills (user_id, date, shop, amount, note, currency) VALUES (1, '2026-07-26', 'Rent', 9000, '', 'SEK')")
    con.commit()
    con.close()

    r = _alembic(path, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    assert "manual_bills still has 1 row" in r.stderr + r.stdout  # said out loud, not silently skipped
    assert "manual_bills" in _tables(path)
    con = sqlite3.connect(path)
    assert con.execute("SELECT shop, amount FROM manual_bills").fetchall() == [("Rent", 9000)]
    con.close()


def test_deleting_an_account_still_works_with_a_leftover_manual_bills_table(client, make_user):
    from sqlalchemy import text

    from app.db import models
    from app.db.database import SessionLocal, engine

    uid, h = make_user()
    other, _ = make_user()
    with engine.begin() as con:
        con.execute(text(
            "CREATE TABLE IF NOT EXISTS manual_bills (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), "
            "date DATE NOT NULL, shop VARCHAR NOT NULL DEFAULT '', amount NUMERIC(12,2) NOT NULL, note VARCHAR NOT NULL DEFAULT '', currency VARCHAR NOT NULL)"
        ))
        con.execute(text("DELETE FROM manual_bills"))
        for u in (uid, other):
            con.execute(text("INSERT INTO manual_bills (user_id, date, shop, amount, note, currency) VALUES (:u, '2026-07-26', 'Rent', 9000, '', 'SEK')"), {"u": u})
    try:
        r = client.post("/api/auth/delete-account", json={"password": "correct-horse-battery"}, headers=h)
        assert r.status_code == 204, r.text
        with engine.begin() as con:
            left = con.execute(text("SELECT user_id FROM manual_bills")).fetchall()
        assert left == [(other,)]  # only the deleted user's rows went
        db = SessionLocal()
        try:
            assert db.get(models.User, uid) is None
        finally:
            db.close()
    finally:
        with engine.begin() as con:
            con.execute(text("DROP TABLE IF EXISTS manual_bills"))
