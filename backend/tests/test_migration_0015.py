"""Migration 0015 against a database that looks like the pre-release schema."""
import os
import sqlite3
import subprocess
import sys
import tempfile

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLES = ["budgets", "income", "recurring_templates", "pending_bills", "manual_bills"]


def _alembic(db_path, *args):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "SECRET_KEY": "m" * 40}
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=BACKEND, env=env, capture_output=True, text=True,
    )


def test_upgrade_backfills_currency_from_owners_base_currency():
    path = os.path.join(tempfile.mkdtemp(), "legacy.db")
    r = _alembic(path, "upgrade", "0014_alert_digest_signature")
    assert r.returncode == 0, r.stderr

    con = sqlite3.connect(path)
    # Turn the fresh DB into the pre-0015 shape (no per-record currency, no fx cache).
    for t in TABLES:
        con.execute(f"ALTER TABLE {t} DROP COLUMN currency")
    con.execute("DROP TABLE fx_rates")
    con.execute("INSERT INTO users (id, email, hashed_password, name) VALUES (1, 'eur@x.com', 'h', 'e'), (2, 'nobody@x.com', 'h', 'n')")
    con.execute(
        "INSERT INTO user_options (user_id, categories, subcategories, units, shops, base_currency, budget_period, budget_rollover) "
        "VALUES (1, '[]', '{}', '[]', '[]', 'EUR', 'Monthly', 0)"
    )  # user 2 has no options row at all
    for uid in (1, 2):
        con.execute("INSERT INTO budgets (user_id, category, amount) VALUES (?, 'Food', 100)", (uid,))
        con.execute("INSERT INTO income (user_id, date, amount, source, note) VALUES (?, '2026-09-01', 5, 'Job', '')", (uid,))
        con.execute("INSERT INTO recurring_templates (user_id, item, category, amount, frequency, note, auto_post) VALUES (?, 'Rent', '', 9, 'Monthly', '', 0)", (uid,))
        con.execute("INSERT INTO pending_bills (user_id, date, shop, amount, note, status, possible_duplicate) VALUES (?, '2026-09-01', 'S', 3, '', 'pending', 0)", (uid,))
        con.execute("INSERT INTO manual_bills (user_id, date, shop, amount, note) VALUES (?, '2026-09-01', 'S', 3, '')", (uid,))
    con.execute("INSERT INTO groups (id, owner_id, name, space_type, currency) VALUES (10, 1, 'House', 'household', 'SEK'), (11, 1, 'Rome', 'trip', 'USD')")
    con.commit()
    con.close()

    r = _alembic(path, "upgrade", "head")
    assert r.returncode == 0, r.stderr

    con = sqlite3.connect(path)
    for t in TABLES:
        rows = dict(con.execute(f"SELECT user_id, currency FROM {t}").fetchall())
        assert rows == {1: "EUR", 2: "SEK"}, (t, rows)
    groups = dict(con.execute('SELECT id, currency FROM "groups"').fetchall())
    assert groups == {10: "EUR", 11: "USD"}  # space follows owner; trip keeps its own currency
    assert con.execute("SELECT count(*) FROM fx_rates").fetchone() == (0,)

    # The temporary column default is gone: a writer that forgets currency fails loudly.
    try:
        con.execute("INSERT INTO budgets (user_id, category, amount) VALUES (1, 'X', 1)")
        raised = False
    except sqlite3.IntegrityError:
        raised = True
    assert raised
    con.close()

    # Running again is a no-op.
    assert _alembic(path, "upgrade", "head").returncode == 0


def test_fresh_database_gets_the_schema_without_errors():
    path = os.path.join(tempfile.mkdtemp(), "fresh.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    con = sqlite3.connect(path)
    cols = {r[1] for r in con.execute("PRAGMA table_info(budgets)")}
    assert "currency" in cols
    assert con.execute("SELECT count(*) FROM fx_rates").fetchone() == (0,)
