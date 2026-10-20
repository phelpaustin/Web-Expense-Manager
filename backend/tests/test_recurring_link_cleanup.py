"""The repair that links old recurring-template expenses to their template (a best-effort heuristic)."""
import datetime as dt

import sqlalchemy as sa

from app.db import models
from app.db.database import SessionLocal
from app.db.recurring_link_cleanup import link_recurring_expenses

TODAY = dt.date.today()


def _template(db, user_id, item="Gym", category="Health", amount=400, last_applied=TODAY, currency="SEK"):
    return db.execute(sa.insert(models.RecurringTemplate.__table__).values(
        user_id=user_id, item=item, category=category, amount=amount, frequency="Monthly", note="", auto_post=False,
        last_applied=last_applied, schedule_anchor=None, currency=currency,
    )).inserted_primary_key[0]


def _expense(db, user_id, description="Gym", category="Health", amount=400, days_ago=10, **over):
    values = dict(user_id=user_id, date=TODAY - dt.timedelta(days=days_ago), category=category, subcategory="", description=description,
                  amount=amount, quantity=1, unit="Count", shop="", brand="", currency="SEK", price_per_unit=amount,
                  bill_total_only=False, source_bill_id=None, group_id=None, recurring_template_id=None)
    values.update(over)
    return db.execute(sa.insert(models.Expense.__table__).values(**values)).inserted_primary_key[0]


def _links(db, user_id):
    rows = db.execute(sa.select(models.Expense.id, models.Expense.recurring_template_id).where(models.Expense.user_id == user_id)).all()
    return dict(rows)


def _run(db):
    n = link_recurring_expenses(db.connection())
    db.commit()
    return n


def test_expenses_that_look_exactly_like_a_templates_are_linked(make_user):
    uid, _ = make_user()
    db = SessionLocal()
    try:
        t = _template(db, uid)
        a, b, c = (_expense(db, uid, days_ago=d) for d in (10, 40, 70))
        db.commit()

        assert _run(db) >= 3

        assert set(_links(db, uid).values()) == {t} and set(_links(db, uid)) == {a, b, c}
    finally:
        db.close()


def test_matching_ignores_case_and_spacing_and_a_blank_template_category_means_recurring(make_user):
    uid, _ = make_user()
    db = SessionLocal()
    try:
        t = _template(db, uid, item="  Gym ", category="")
        ids = [_expense(db, uid, description=d, category="recurring", days_ago=n) for d, n in (("gym", 5), (" GYM", 35))]
        db.commit()

        _run(db)

        assert [_links(db, uid)[i] for i in ids] == [t, t]
    finally:
        db.close()


def test_one_coincidence_is_not_enough(make_user):
    uid, _ = make_user()
    db = SessionLocal()
    try:
        _template(db, uid)
        only = _expense(db, uid)
        db.commit()

        _run(db)

        assert _links(db, uid)[only] is None
    finally:
        db.close()


def test_anything_that_differs_is_left_alone(make_user):
    uid, _ = make_user()
    db = SessionLocal()
    try:
        _template(db, uid, last_applied=TODAY - dt.timedelta(days=20))
        real = [_expense(db, uid, days_ago=30), _expense(db, uid, days_ago=60)]
        different = {
            "other amount": _expense(db, uid, amount=401),
            "other category": _expense(db, uid, category="Fun"),
            "other description": _expense(db, uid, description="Gym membership"),
            "other currency": _expense(db, uid, currency="EUR"),
            "has a shop": _expense(db, uid, shop="Nordic Gym"),
            "has a brand": _expense(db, uid, brand="X"),
            "has a subcategory": _expense(db, uid, subcategory="Sport"),
            "bought in bulk": _expense(db, uid, quantity=2),
            "other unit": _expense(db, uid, unit="Kg"),
            "from a bill": _expense(db, uid, bill_total_only=True),
            "in a shared space": _expense(db, uid, group_id=1),
            "after the last application": _expense(db, uid, days_ago=5),
        }
        db.commit()

        _run(db)

        links = _links(db, uid)
        assert all(links[i] is not None for i in real)
        assert {name: links[i] for name, i in different.items() if links[i] is not None} == {}
    finally:
        db.close()


def test_two_identical_templates_cannot_be_told_apart_so_nothing_is_linked(make_user):
    uid, _ = make_user()
    db = SessionLocal()
    try:
        _template(db, uid)
        _template(db, uid)
        ids = [_expense(db, uid, days_ago=d) for d in (10, 40)]
        db.commit()

        _run(db)

        assert [_links(db, uid)[i] for i in ids] == [None, None]
    finally:
        db.close()


def test_a_template_that_was_never_applied_links_nothing(make_user):
    uid, _ = make_user()
    db = SessionLocal()
    try:
        _template(db, uid, last_applied=None)
        ids = [_expense(db, uid, days_ago=d) for d in (10, 40)]
        db.commit()

        _run(db)

        assert [_links(db, uid)[i] for i in ids] == [None, None]
    finally:
        db.close()


def test_each_user_only_links_to_their_own_templates_and_existing_links_stay(make_user):
    alice, _ = make_user()
    bob, _ = make_user()
    db = SessionLocal()
    try:
        ta = _template(db, alice)
        mine = [_expense(db, alice, days_ago=d) for d in (10, 40)]
        theirs = [_expense(db, bob, days_ago=d) for d in (10, 40)]           # Bob has no such template
        linked_already = _expense(db, alice, days_ago=70, recurring_template_id=999)
        db.commit()

        _run(db)

        assert [_links(db, alice)[i] for i in mine] == [ta, ta]
        assert [_links(db, bob)[i] for i in theirs] == [None, None]
        assert _links(db, alice)[linked_already] == 999
    finally:
        db.close()


def test_running_it_again_changes_nothing(make_user):
    uid, _ = make_user()
    db = SessionLocal()
    try:
        _template(db, uid)
        [_expense(db, uid, days_ago=d) for d in (10, 40)]
        db.commit()
        assert _run(db) >= 2

        assert _run(db) == 0
    finally:
        db.close()
