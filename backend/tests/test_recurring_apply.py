"""Applying recurring templates must post each expense once, even when requests overlap
(two tabs, a retry, a double click). The schedule is advanced with a compare-and-swap,
so only the request that wins the claim posts anything."""
import datetime
import threading

from app.api import recurring as recurring_api
from app.db import models
from app.db.database import SessionLocal

TODAY = datetime.date.today


def _template(client, headers, *, item="Gym", frequency="Daily", days_since_applied=3):
    """A template whose last application was `days_since_applied` days ago (None = never)."""
    t = client.post("/api/recurring", json={"item": item, "amount": "5", "frequency": frequency}, headers=headers).json()
    if days_since_applied is not None:
        db = SessionLocal()
        try:
            row = db.get(models.RecurringTemplate, t["id"])
            row.last_applied = TODAY() - datetime.timedelta(days=days_since_applied)
            row.schedule_anchor = None
            db.commit()
        finally:
            db.close()
    return t["id"]


def _posted(user_id, item="Gym"):
    db = SessionLocal()
    try:
        rows = db.query(models.Expense).filter(models.Expense.user_id == user_id, models.Expense.description == item).all()
        return sorted(r.date for r in rows)
    finally:
        db.close()


def _in_parallel(n, fn):
    barrier = threading.Barrier(n)
    results = [None] * n

    def run(i):
        barrier.wait()
        results[i] = fn()

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return results


def test_apply_posts_one_expense_dated_today_and_advances_the_schedule(client, make_user):
    uid, h = make_user()
    tid = _template(client, h, days_since_applied=None)

    r = client.post(f"/api/recurring/{tid}/apply", headers=h)

    assert r.status_code == 200 and r.json()["applied"] == 1
    assert _posted(uid) == [TODAY()]
    t = client.get("/api/recurring", headers=h).json()[0]
    assert t["last_applied"] == TODAY().isoformat()


def test_apply_due_posts_every_missed_period_once_and_is_idempotent(client, make_user):
    uid, h = make_user()
    _template(client, h, days_since_applied=3)

    first = client.post("/api/recurring/apply-due", headers=h).json()
    second = client.post("/api/recurring/apply-due", headers=h).json()

    assert first["applied"] == 3
    assert second["applied"] == 0
    assert _posted(uid) == [TODAY() - datetime.timedelta(days=d) for d in (2, 1, 0)]


def test_overlapping_apply_due_requests_post_each_period_once(client, make_user):
    uid, h = make_user()
    # Repeat with fresh templates: the overlap is timing-dependent, so give it many chances.
    for round_no in range(8):
        item = f"Gym{round_no}"
        _template(client, h, item=item, days_since_applied=3)

        results = _in_parallel(6, lambda: client.post("/api/recurring/apply-due", headers=h))

        assert all(r.status_code == 200 for r in results), [r.status_code for r in results]
        assert len(_posted(uid, item)) == 3, f"round {round_no}: duplicates were posted"


def test_apply_loses_with_409_when_another_request_applies_between_read_and_claim(client, make_user, monkeypatch):
    """Forces the overlap: a competing request applies the template right after this
    request has read it, so this request's claim must lose and post nothing."""
    uid, h = make_user()
    tid = _template(client, h, days_since_applied=None)
    real = recurring_api._get_owned_or_404
    fired = []

    def read_then_lose_the_race(db, template_id, user_id):
        template = real(db, template_id, user_id)
        if not fired:
            fired.append(True)
            assert client.post(f"/api/recurring/{tid}/apply", headers=h).status_code == 200  # the winner
        return template

    monkeypatch.setattr(recurring_api, "_get_owned_or_404", read_then_lose_the_race)

    r = client.post(f"/api/recurring/{tid}/apply", headers=h)

    assert r.status_code == 409
    assert _posted(uid) == [TODAY()]  # only the winner posted


def test_apply_due_skips_a_template_another_request_applied_between_read_and_claim(client, make_user, monkeypatch):
    uid, h = make_user()
    _template(client, h, days_since_applied=3)
    real = recurring_api.rec.due_dates
    fired = []

    def compute_then_lose_the_race(*args, **kwargs):
        dates = real(*args, **kwargs)  # this request has decided to post these dates...
        if not fired:
            fired.append(True)
            assert client.post("/api/recurring/apply-due", headers=h).json()["applied"] == 3  # ...but another got there first
        return dates

    monkeypatch.setattr(recurring_api.rec, "due_dates", compute_then_lose_the_race)

    r = client.post("/api/recurring/apply-due", headers=h)

    assert r.status_code == 200 and r.json()["applied"] == 0
    assert len(_posted(uid)) == 3  # not 6


def test_a_request_holding_stale_state_loses_the_claim(client, make_user):
    """Deterministic version of the race: this request read the template, then another
    request applied it before this one tried to claim."""
    uid, h = make_user()
    tid = _template(client, h, days_since_applied=3)

    stale = SessionLocal()
    try:
        template = stale.get(models.RecurringTemplate, tid)  # reads last_applied = 3 days ago
        assert client.post("/api/recurring/apply-due", headers=h).json()["applied"] == 3  # the other request wins

        won = recurring_api._claim(stale, template, last_applied=TODAY(), schedule_anchor=TODAY())
        stale.rollback()
    finally:
        stale.close()

    assert won is False
    assert len(_posted(uid)) == 3  # nothing extra


def test_claim_works_for_a_never_applied_template(client, make_user):
    """last_applied is NULL here; `= NULL` never matches in SQL, so the claim must use IS NULL."""
    uid, h = make_user()
    tid = _template(client, h, days_since_applied=None)

    db = SessionLocal()
    try:
        template = db.get(models.RecurringTemplate, tid)
        assert recurring_api._claim(db, template, last_applied=TODAY(), schedule_anchor=TODAY()) is True
        db.commit()
    finally:
        db.close()
