"""Parallel first requests for a brand-new user must not fail on the options row.

The dashboard fires many requests at once on first load and nearly all of them
call get_or_create_options; they used to race and hit the unique user_id constraint.
"""
import threading

from app.api.options import get_or_create_options
from app.db import models
from app.db.database import SessionLocal


def test_concurrent_first_use_creates_exactly_one_options_row(make_user):
    user_id, _ = make_user()
    threads_n = 14
    barrier = threading.Barrier(threads_n)
    errors: list[Exception] = []
    ids: list[int] = []

    def worker():
        db = SessionLocal()
        try:
            barrier.wait()
            ids.append(get_or_create_options(db, user_id).id)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=worker) for _ in range(threads_n)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert errors == []
    assert len(set(ids)) == 1
    db = SessionLocal()
    try:
        assert db.query(models.UserOptions).filter(models.UserOptions.user_id == user_id).count() == 1
    finally:
        db.close()


def test_defaults_are_unchanged_for_a_new_user(make_user):
    user_id, _ = make_user()
    db = SessionLocal()
    try:
        opts = get_or_create_options(db, user_id)
        assert opts.base_currency == "SEK"
        assert opts.count_bills_as_spending is True
        assert opts.alert_digest_enabled is True
        assert opts.budget_period == "Monthly"
        assert "Groceries" in opts.categories
    finally:
        db.close()
