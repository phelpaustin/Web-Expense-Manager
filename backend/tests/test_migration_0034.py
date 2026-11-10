"""Migration 0034: names marked "not a subscription"."""
import os
import sqlite3
import tempfile

from tests.test_migration_0015 import _alembic
from tests.test_migration_0030 import _columns, _tables


def test_a_fresh_database_has_the_table_and_one_name_per_user():
    path = os.path.join(tempfile.mkdtemp(), "fresh34.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    assert "ignored_subscriptions" in _tables(path)
    assert set(_columns(path, "ignored_subscriptions")) == {"id", "user_id", "key", "name"}
    con = sqlite3.connect(path)
    for i in (1, 2):
        con.execute("INSERT INTO users (id, email, hashed_password, name) VALUES (?, ?, 'h', 'a')", (i, f"a{i}@x.com"))
    row = "INSERT INTO ignored_subscriptions (user_id, key, name) VALUES (?, 'gym', 'Gym')"
    con.execute(row, (1,))
    con.execute(row, (2,))
    try:
        con.execute(row, (1,))
        raised = False
    except sqlite3.IntegrityError:
        raised = True
    con.close()
    assert raised


def test_the_downgrade_removes_it_and_the_upgrade_brings_it_back():
    path = os.path.join(tempfile.mkdtemp(), "down34.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    assert _alembic(path, "downgrade", "0033_sign_in_events").returncode == 0
    assert "ignored_subscriptions" not in _tables(path)
    assert _alembic(path, "upgrade", "head").returncode == 0
    assert "ignored_subscriptions" in _tables(path)
    assert _alembic(path, "upgrade", "head").returncode == 0
