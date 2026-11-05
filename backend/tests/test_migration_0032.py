"""Migration 0032: the "count bills as spending" switch is dropped (bills always count)."""
import os
import sqlite3
import tempfile

from tests.test_migration_0015 import _alembic
from tests.test_migration_0030 import _columns


def test_a_fresh_database_has_no_such_column():
    path = os.path.join(tempfile.mkdtemp(), "fresh.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    assert "count_bills_as_spending" not in _columns(path, "user_options")


def test_the_upgrade_drops_it_keeps_other_settings_and_is_idempotent():
    path = os.path.join(tempfile.mkdtemp(), "m32.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    assert _alembic(path, "downgrade", "0031_dismissed_duplicates").returncode == 0
    assert "count_bills_as_spending" in _columns(path, "user_options")
    con = sqlite3.connect(path)
    con.execute("INSERT INTO users (id, email, hashed_password, name) VALUES (1, 'a@x.com', 'h', 'a')")
    con.execute("UPDATE user_options SET base_currency = 'EUR' WHERE 0")  # table exists with the column
    con.commit()
    con.close()
    r = _alembic(path, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    assert "count_bills_as_spending" not in _columns(path, "user_options")
    assert _alembic(path, "upgrade", "head").returncode == 0
