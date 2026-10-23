"""Editing many expenses together: by id, or by everything a search & filter matches."""
from app.db import models
from app.db.database import SessionLocal
from tests.test_group_member_data import _accept_all, _email, _group_with_member


def _expense(client, h, **kw):
    body = {"date": "2026-01-30", "category": "Uncategorized", "description": "3365060581", "shop": "UNIONEN",
            "amount": 235, "currency": "SEK"}
    body.update(kw)
    r = client.post("/api/expenses", json=body, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _row(eid):
    db = SessionLocal()
    try:
        e = db.get(models.Expense, eid)
        return {"category": e.category, "subcategory": e.subcategory, "shop": e.shop, "description": e.description,
                "group_id": e.group_id, "amount": float(e.amount), "date": str(e.date)}
    finally:
        db.close()


def _bulk(client, h, body):
    return client.post("/api/expenses/bulk-update", json=body, headers=h)


def test_changes_the_chosen_fields_on_every_id_and_nothing_else(client, make_user):
    _, h = make_user()
    ids = [_expense(client, h, date=f"2026-0{m}-28") for m in (1, 2, 3)]
    r = _bulk(client, h, {"ids": ids, "changes": {"category": "Membership", "subcategory": "Union"}})
    assert r.status_code == 200 and r.json() == {"updated": 3}
    for i, m in zip(ids, (1, 2, 3)):
        row = _row(i)
        assert (row["category"], row["subcategory"]) == ("Membership", "Union")
        assert row["shop"] == "UNIONEN" and row["amount"] == 235 and row["date"] == f"2026-0{m}-28"


def test_everything_matching_a_filter_is_changed_across_pages(client, make_user):
    _, h = make_user()
    union = [_expense(client, h, date=f"2026-{m:02d}-15") for m in range(1, 10)]
    other = _expense(client, h, shop="ICA", description="milk")
    r = _bulk(client, h, {"filters": {"search": "union", "date_from": "2026-02-01", "date_to": "2026-08-31"},
                          "changes": {"category": "Membership"}})
    assert r.json() == {"updated": 7}  # Feb..Aug only
    assert [_row(i)["category"] for i in union] == ["Uncategorized"] + ["Membership"] * 7 + ["Uncategorized"]
    assert _row(other)["category"] == "Uncategorized"


def test_all_or_nothing_when_one_expense_is_not_theirs(client, make_user):
    _, mine = make_user()
    _, theirs = make_user()
    a = _expense(client, mine)
    b = _expense(client, theirs)
    r = _bulk(client, mine, {"ids": [a, b], "changes": {"category": "Membership"}})
    assert r.status_code == 404
    assert _row(a)["category"] == "Uncategorized"  # untouched


def test_a_viewer_cannot_bulk_edit_a_space(client, make_user):
    gid, (oid, oh), (vid, vh) = _group_with_member(client, make_user, role="viewer")
    eid = _expense(client, oh, group_id=gid)
    assert _bulk(client, vh, {"ids": [eid], "changes": {"category": "X"}}).status_code == 403
    assert _row(eid)["category"] == "Uncategorized"


def test_an_editor_may_edit_only_their_own_in_a_space_and_nothing_changes_otherwise(client, make_user):
    gid, (oid, oh), (eid_, eh) = _group_with_member(client, make_user, role="editor")
    mine = _expense(client, eh, group_id=gid)
    owners = _expense(client, oh, group_id=gid)
    r = _bulk(client, eh, {"ids": [mine, owners], "changes": {"category": "X"}})
    assert r.status_code == 403
    assert _row(mine)["category"] == "Uncategorized" and _row(owners)["category"] == "Uncategorized"
    assert _bulk(client, eh, {"ids": [mine], "changes": {"category": "X"}}).json() == {"updated": 1}


def test_can_move_many_into_a_space_and_back_to_personal(client, make_user):
    _, h = make_user()
    gid = client.post("/api/groups", json={"name": "Home"}, headers=h).json()["id"]
    ids = [_expense(client, h) for _ in range(3)]
    assert _bulk(client, h, {"ids": ids, "changes": {"group_id": gid}}).json() == {"updated": 3}
    assert {_row(i)["group_id"] for i in ids} == {gid}
    assert _bulk(client, h, {"ids": ids, "changes": {"group_id": None}}).json() == {"updated": 3}
    assert {_row(i)["group_id"] for i in ids} == {None}


def test_never_touches_another_users_expenses_through_a_filter(client, make_user):
    _, mine = make_user()
    _, other = make_user()
    a = _expense(client, mine)
    b = _expense(client, other)
    assert _bulk(client, mine, {"filters": {"search": "union"}, "changes": {"category": "Membership"}}).json() == {"updated": 1}
    assert _row(a)["category"] == "Membership" and _row(b)["category"] == "Uncategorized"


def test_new_category_and_shop_become_options(client, make_user):
    _, h = make_user()
    a = _expense(client, h)
    _bulk(client, h, {"ids": [a], "changes": {"category": "Membership", "shop": "Unionen AB"}})
    opts = client.get("/api/options", headers=h).json()
    assert "Membership" in opts["categories"] and "Unionen AB" in opts["shops"]


def test_a_changed_shop_keeps_the_derived_bills_in_step(client, make_user):
    from decimal import Decimal as D
    from tests.test_bill_sync import _add, _all_bills

    _, h = make_user()
    a = _add(client, h, amount="10", shop="ICA")
    b = _add(client, h, amount="20", shop="ICA")
    _add(client, h, amount="7", shop="Coop")
    assert _bulk(client, h, {"ids": [a["id"], b["id"]], "changes": {"shop": "Coop"}}).json() == {"updated": 2}
    [bill] = _all_bills(client, h)  # ICA is gone: all three are one Coop bill now
    assert bill["shop"] == "Coop" and D(str(bill["amount"])) == D("37") and bill["item_count"] == 3


def test_rejects_bad_requests(client, make_user):
    _, h = make_user()
    a = _expense(client, h)
    assert _bulk(client, h, {"ids": [a], "changes": {}}).status_code == 422  # nothing to change
    assert _bulk(client, h, {"changes": {"category": "X"}}).status_code == 422  # no target
    assert _bulk(client, h, {"ids": [a], "filters": {}, "changes": {"category": "X"}}).status_code == 422  # both
    assert _bulk(client, h, {"ids": [a], "changes": {"category": None}}).status_code == 422
    assert _bulk(client, h, {"ids": [a], "changes": {"amount": 1}}).status_code == 422  # not a bulk-editable field
    assert _bulk(client, h, {"ids": [a], "changes": {"amount": 1, "category": "X"}}).status_code == 200
    assert _row(a)["amount"] == 235 and _row(a)["category"] == "X"  # amount is ignored, never bulk-set
    assert _bulk(client, h, {"ids": [], "changes": {"category": "X"}}).status_code == 422


def test_requires_login(client):
    assert client.post("/api/expenses/bulk-update", json={"ids": [1], "changes": {"category": "X"}}).status_code == 401
