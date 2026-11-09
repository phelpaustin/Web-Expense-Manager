"""Migration 0033: the sign-in history table."""
import os
import tempfile

from tests.test_migration_0015 import _alembic
from tests.test_migration_0030 import _columns, _tables


def test_a_fresh_database_has_the_table():
    path = os.path.join(tempfile.mkdtemp(), "fresh33.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    assert "sign_in_events" in _tables(path)
    cols = _columns(path, "sign_in_events")
    assert set(cols) == {"id", "user_id", "at", "method", "success", "ip", "user_agent"}
    assert all(cols[c][1] == 1 for c in ("user_id", "at", "method", "success"))


def test_the_downgrade_removes_it_and_the_upgrade_brings_it_back():
    path = os.path.join(tempfile.mkdtemp(), "down33.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    assert _alembic(path, "downgrade", "0032_drop_count_bills").returncode == 0
    assert "sign_in_events" not in _tables(path)
    r = _alembic(path, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    assert "sign_in_events" in _tables(path)
    assert _alembic(path, "upgrade", "head").returncode == 0  # idempotent
