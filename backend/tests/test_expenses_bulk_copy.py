"""Copying expenses into a space (e.g. bank-statement rows into a trip)."""
from app.db import models
from app.db.database import SessionLocal
from tests.test_expenses_bulk_update import _expense, _row
from tests.test_group_member_data import _group_with_member


def _copy(client, h, body):
    return client.post("/api/expenses/bulk-copy", json=body, headers=h)


def _all_rows():
    db = SessionLocal()
    try:
        return [
            {"id": e.id, "user_id": e.user_id, "group_id": e.group_id, "amount": float(e.amount), "shop": e.shop,
             "category": e.category, "source_bill_id": e.source_bill_id, "recurring_template_id": e.recurring_template_id,
             "currency": e.currency, "date": str(e.date)}
            for e in db.query(models.Expense).order_by(models.Expense.id).all()
        ]
    finally:
        db.close()


def _trip(client, h, name="Goa"):
    return client.post("/api/groups", json={"name": name}, headers=h).json()["id"]


def test_copies_into_the_space_and_leaves_the_originals_alone(client, make_user):
    _, h = make_user()
    gid = _trip(client, h)
    a = _expense(client, h, category="Trip", shop="HOTEL", amount=1200, date="2026-02-01")
    b = _expense(client, h, category="Trip", shop="TAXI", amount=300, date="2026-02-02")
    before = {i: _row(i) for i in (a, b)}

    res = _copy(client, h, {"ids": [a, b], "group_id": gid})
    assert res.status_code == 200, res.text
    assert res.json() == {"copied": 2, "skipped": 0}

    assert {i: _row(i) for i in (a, b)} == before  # originals unchanged, still personal
    copies = [r for r in _all_rows() if r["group_id"] == gid]
    assert sorted((r["shop"], r["amount"], r["date"], r["currency"]) for r in copies) == [
        ("HOTEL", 1200.0, "2026-02-01", "SEK"),
        ("TAXI", 300.0, "2026-02-02", "SEK"),
    ]
    assert all(r["category"] == "Trip" and r["source_bill_id"] is None and r["recurring_template_id"] is None for r in copies)


def test_rows_already_in_that_space_are_skipped_so_a_double_click_cannot_double_them(client, make_user):
    _, h = make_user()
    gid = _trip(client, h)
    a = _expense(client, h, shop="HOTEL")
    inside = _expense(client, h, shop="TAXI", group_id=gid)
    res = _copy(client, h, {"ids": [a, inside], "group_id": gid})
    assert res.json() == {"copied": 1, "skipped": 1}
    assert len([r for r in _all_rows() if r["group_id"] == gid]) == 2


def test_copies_everything_a_filter_matches(client, make_user):
    _, h = make_user()
    gid = _trip(client, h)
    _expense(client, h, category="Trip", shop="HOTEL")
    _expense(client, h, category="Trip", shop="TAXI")
    _expense(client, h, category="Food", shop="ICA")
    res = _copy(client, h, {"filters": {"category": "trip"}, "group_id": gid})
    assert res.json() == {"copied": 2, "skipped": 0}
    assert sorted(r["shop"] for r in _all_rows() if r["group_id"] == gid) == ["HOTEL", "TAXI"]


def test_a_viewer_cannot_copy_into_a_space_and_nothing_is_created(client, make_user):
    gid, (oid, oh), (vid, vh) = _group_with_member(client, make_user, role="viewer")
    mine = _expense(client, vh, shop="HOTEL")
    count = len(_all_rows())
    res = _copy(client, vh, {"ids": [mine], "group_id": gid})
    assert res.status_code == 403
    assert len(_all_rows()) == count


def test_all_or_nothing_when_one_source_is_not_visible(client, make_user):
    _, h = make_user()
    _, other = make_user()
    gid = _trip(client, h)
    mine = _expense(client, h, shop="HOTEL")
    theirs = _expense(client, other, shop="SECRET")
    count = len(_all_rows())
    res = _copy(client, h, {"ids": [mine, theirs], "group_id": gid})
    assert res.status_code == 404
    assert len(_all_rows()) == count


def test_can_copy_a_shared_spaces_expense_into_a_trip_as_your_own(client, make_user):
    gid, (oid, oh), (eid, eh) = _group_with_member(client, make_user, role="editor")
    theirs = _expense(client, oh, shop="DINNER", group_id=gid)
    trip = _trip(client, eh, "Oslo")
    res = _copy(client, eh, {"ids": [theirs], "group_id": trip})
    assert res.json() == {"copied": 1, "skipped": 0}
    copy = next(r for r in _all_rows() if r["group_id"] == trip)
    assert copy["user_id"] == eid
    assert _row(theirs)["group_id"] == gid  # the original stays where it was


def test_rejects_bad_requests(client, make_user):
    _, h = make_user()
    gid = _trip(client, h)
    e = _expense(client, h)
    assert _copy(client, h, {"group_id": gid}).status_code == 422                      # no target
    assert _copy(client, h, {"ids": [e], "filters": {}, "group_id": gid}).status_code == 422  # both
    assert _copy(client, h, {"ids": [], "group_id": gid}).status_code == 422
    assert _copy(client, h, {"ids": [e]}).status_code == 422                           # no space
    assert _copy(client, h, {"ids": [e], "group_id": 99999}).status_code in (403, 404)


def test_requires_login(client):
    assert _copy(client, {}, {"ids": [1], "group_id": 1}).status_code in (401, 403)
