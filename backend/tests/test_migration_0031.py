"""Migration 0031: the dismissed duplicates table."""
import os
import sqlite3
import tempfile

from tests.test_migration_0015 import _alembic
from tests.test_migration_0030 import _columns, _tables


def _db_at_0030():
    path = os.path.join(tempfile.mkdtemp(), "m31.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    assert _alembic(path, "downgrade", "0030_savings_goals").returncode == 0
    return path


def test_a_fresh_database_has_the_table():
    path = os.path.join(tempfile.mkdtemp(), "fresh.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    assert "dismissed_duplicates" in _tables(path)
    cols = _columns(path, "dismissed_duplicates")
    assert set(cols) == {"id", "user_id", "key", "day", "count"}
    assert all(cols[c][1] == 1 for c in ("user_id", "key", "day", "count"))       # all required


def test_one_key_per_user_is_enforced():
    path = os.path.join(tempfile.mkdtemp(), "uq.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    con = sqlite3.connect(path)
    for i in (1, 2):
        con.execute("INSERT INTO users (id, email, hashed_password, name) VALUES (?, ?, 'h', 'a')", (i, f"a{i}@x.com"))
    row = "INSERT INTO dismissed_duplicates (user_id, key, day, count) VALUES (?, ?, '2026-10-01', 2)"
    con.execute(row, (1, "k"))
    con.execute(row, (2, "k"))                                                    # another user may use the same key
    try:
        con.execute(row, (1, "k"))
        raised = False
    except sqlite3.IntegrityError:
        raised = True
    con.close()
    assert raised


def test_the_downgrade_removes_it_and_the_upgrade_brings_it_back():
    path = _db_at_0030()
    assert "dismissed_duplicates" not in _tables(path) and "savings_goals" in _tables(path)
    r = _alembic(path, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    assert "dismissed_duplicates" in _tables(path)
    assert _alembic(path, "upgrade", "head").returncode == 0                      # idempotent


def test_the_upgrade_leaves_other_rows_alone():
    path = _db_at_0030()
    con = sqlite3.connect(path)
    con.execute("INSERT INTO users (id, email, hashed_password, name) VALUES (1, 'a@x.com', 'h', 'a')")
    con.execute("INSERT INTO savings_goals (id, user_id, name, target_amount, currency, note) VALUES (1, 1, 'Trip', 1000, 'SEK', '')")
    con.commit()
    con.close()
    assert _alembic(path, "upgrade", "head").returncode == 0
    con = sqlite3.connect(path)
    assert con.execute("SELECT name FROM savings_goals").fetchall() == [("Trip",)]
    con.close()


def test_the_downgrade_works_with_rows_in_place():
    path = os.path.join(tempfile.mkdtemp(), "with.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    con = sqlite3.connect(path)
    con.execute("INSERT INTO users (id, email, hashed_password, name) VALUES (1, 'a@x.com', 'h', 'a')")
    con.execute("INSERT INTO dismissed_duplicates (user_id, key, day, count) VALUES (1, 'k', '2026-10-01', 2)")
    con.commit()
    con.close()
    r = _alembic(path, "downgrade", "0030_savings_goals")
    assert r.returncode == 0, r.stderr
    assert "dismissed_duplicates" not in _tables(path)
