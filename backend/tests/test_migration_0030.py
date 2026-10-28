"""Migration 0030: the savings goal tables."""
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


def _columns(path, table):
    con = sqlite3.connect(path)
    try:
        return {r[1]: (r[2], r[3]) for r in con.execute(f"PRAGMA table_info({table})")}     # name -> (type, notnull)
    finally:
        con.close()


def _db_at_0029():
    path = os.path.join(tempfile.mkdtemp(), "m30.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    assert _alembic(path, "downgrade", "0029_expense_trip_days").returncode == 0
    return path


def test_a_fresh_database_has_both_tables():
    path = os.path.join(tempfile.mkdtemp(), "fresh.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    assert {"savings_goals", "savings_contributions"} <= _tables(path)
    assert set(_columns(path, "savings_goals")) == {"id", "user_id", "name", "target_amount", "currency", "target_date", "note"}
    assert set(_columns(path, "savings_contributions")) == {"id", "goal_id", "user_id", "date", "amount", "note"}


def test_the_downgrade_removes_them_and_the_upgrade_brings_them_back():
    path = _db_at_0029()
    assert not ({"savings_goals", "savings_contributions"} & _tables(path))
    r = _alembic(path, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    assert {"savings_goals", "savings_contributions"} <= _tables(path)
    assert _alembic(path, "upgrade", "head").returncode == 0               # idempotent
    assert _columns(path, "savings_goals")["target_date"][1] == 0           # the date is optional
    assert _columns(path, "savings_goals")["target_amount"][1] == 1         # the target is not


def test_the_upgrade_leaves_other_tables_and_rows_alone():
    path = _db_at_0029()
    con = sqlite3.connect(path)
    con.execute("INSERT INTO users (id, email, hashed_password, name) VALUES (1, 'a@x.com', 'h', 'a')")
    con.execute("INSERT INTO income (user_id, date, amount, source, note, currency) VALUES (1, '2026-10-01', 100, 'Job', '', 'SEK')")
    con.commit()
    con.close()
    assert _alembic(path, "upgrade", "head").returncode == 0
    con = sqlite3.connect(path)
    assert con.execute("SELECT source FROM income").fetchall() == [("Job",)]
    con.close()


def test_the_downgrade_works_even_with_goals_in_place():
    path = os.path.join(tempfile.mkdtemp(), "with.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    con = sqlite3.connect(path)
    con.execute("INSERT INTO users (id, email, hashed_password, name) VALUES (1, 'a@x.com', 'h', 'a')")
    con.execute("INSERT INTO savings_goals (id, user_id, name, target_amount, currency, note) VALUES (1, 1, 'Trip', 1000, 'SEK', '')")
    con.execute("INSERT INTO savings_contributions (goal_id, user_id, date, amount, note) VALUES (1, 1, '2026-10-01', 100, '')")
    con.commit()
    con.close()
    r = _alembic(path, "downgrade", "0029_expense_trip_days")
    assert r.returncode == 0, r.stderr
    assert not ({"savings_goals", "savings_contributions"} & _tables(path))
