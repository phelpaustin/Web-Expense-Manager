"""There is no demo account or seed data any more, and an old one can be removed with one command."""
import datetime as dt

import pytest

from app.db import models
from app.db.database import SessionLocal
from app.scripts import remove_demo_account


def test_app_start_creates_no_demo_account(client):
    # `client` runs the real startup. On SQLite, older versions seeded demo@example.com / demo1234 here.
    with SessionLocal() as db:
        assert db.query(models.User).filter(models.User.email == "demo@example.com").count() == 0


def test_no_seed_module_is_left():
    with pytest.raises(ModuleNotFoundError):
        __import__("app.db.seed")


def _add_account(email):
    with SessionLocal() as db:
        user = models.User(email=email, hashed_password="x", name="", email_verified=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        db.add(models.Expense(
            user_id=user.id, date=dt.date(2026, 6, 4), category="Groceries",
            description="Supermarket", amount=74.10, price_per_unit=74.10,
        ))
        db.add(models.Budget(user_id=user.id, category="Groceries", amount=100.0, currency="SEK"))
        db.commit()
        return user.id


def _exists(email):
    with SessionLocal() as db:
        return db.query(models.User).filter(models.User.email == email).count() == 1


def test_script_defaults_to_the_old_demo_address():
    assert remove_demo_account.DEFAULT_EMAIL == "demo@example.com"


def test_script_dry_run_changes_nothing(capsys):
    email = "old-demo-dry@example.com"
    _add_account(email)
    assert remove_demo_account.main(["--email", email]) == 0
    assert "Dry run" in capsys.readouterr().out
    assert _exists(email)


def test_script_delete_removes_the_account_and_its_data(capsys):
    email = "old-demo-delete@example.com"
    uid = _add_account(email)
    other_uid = _add_account("someone-else@example.com")
    assert remove_demo_account.main(["--email", email, "--delete"]) == 0
    assert "Removed" in capsys.readouterr().out
    assert not _exists(email)
    with SessionLocal() as db:
        assert db.query(models.Expense).filter(models.Expense.user_id == uid).count() == 0
        assert db.query(models.Budget).filter(models.Budget.user_id == uid).count() == 0
        # another account is untouched
        assert db.query(models.Expense).filter(models.Expense.user_id == other_uid).count() == 1


def test_script_with_no_such_account_is_a_no_op(capsys):
    assert remove_demo_account.main(["--email", "nobody-here@example.com", "--delete"]) == 0
    assert "Nothing to do" in capsys.readouterr().out
