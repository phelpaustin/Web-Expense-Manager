"""Full backup and restore: bills stay containers, nothing is regrouped, nothing is lost."""
import datetime as dt
import io
import json
import zipfile
from decimal import Decimal

import pytest

from app.core.rate_limit import limiter
from app.db import models
from app.db.database import SessionLocal
from tests.test_bill_sync import _add, _all_bills, _bill_of, _insert, _legacy_bill, _sync
from tests.test_bills_workflow import PDF, TODAY, _bill, _bills, _expenses, _items, _spent

D = Decimal


@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.reset()  # many restores from one "visitor"
    yield
    limiter.reset()


def _download(client, h):
    r = client.get("/api/backup", headers=h)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    return r.content


def _restore(client, h, content, name="backup.zip"):
    return client.post("/api/backup/restore", files={"file": (name, content, "application/zip")}, headers=h)


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data if isinstance(data, (bytes, str)) else json.dumps(data))
    return buf.getvalue()


def _shape(client, h):
    """What the user sees, without ids."""
    bills = sorted(
        (b["shop"], str(D(str(b["amount"]))), b["status"], b["item_count"], b["has_receipt"], b["from_expenses"])
        for b in _all_bills(client, h)
    )
    expenses = sorted((e["description"], e["shop"], str(D(str(e["amount"]))), e["bill_total_only"]) for e in _expenses(client, h))
    return bills, expenses


def _populate(client, h, uid):
    _add(client, h, amount="10", shop="Lidl", description="Milk")
    _add(client, h, amount="20", shop="Lidl", description="Bread")  # same day, same shop: separate purchases
    big = _bill(client, h, shop="Ikea", amount="100")
    assert client.post("/api/expenses/bulk", json={"items": _items(60, 30, 10, shop="Ikea"), "bill_id": big["id"]}, headers=h).status_code == 201
    with_receipt = _bill(client, h, shop="Phone", amount="45")
    assert client.post(f"/api/pending-bills/{with_receipt['id']}/receipt", files={"file": ("p.pdf", PDF, "application/pdf")}, headers=h).status_code == 200
    ids = _insert(uid, [{"shop": "Coop", "amount": 7, "description": "A"}, {"shop": "Coop", "amount": 3, "description": "B"}])
    _legacy_bill(uid, ids, shop="Coop")
    db = SessionLocal()
    db.add(models.Budget(user_id=uid, category="Food", amount=500, currency="SEK"))
    db.add(models.Income(user_id=uid, date=dt.date(2026, 7, 1), amount=1000, source="Pay", note="", currency="SEK"))
    goal = models.SavingsGoal(user_id=uid, name="Trip", target_amount=900, currency="SEK", note="")
    db.add(goal)
    db.flush()
    db.add(models.SavingsContribution(goal_id=goal.id, user_id=uid, date=dt.date(2026, 7, 2), amount=50, note=""))
    db.commit()
    db.close()
    client.post("/api/recurring", json={"item": "Gym", "amount": "30", "frequency": "Monthly"}, headers=h)
    _sync(client, h)


def test_a_restored_account_looks_the_same_with_bills_as_containers(client, make_user):
    uid, h = make_user()
    _populate(client, h, uid)
    before = _shape(client, h)
    spent = _spent(client, h)
    data = _download(client, h)

    _, h2 = make_user()
    r = _restore(client, h2, data)
    assert r.status_code == 200, r.text
    assert r.json()["bills"] == len(before[0]) and r.json()["receipts"] == 1
    assert _shape(client, h2) == before
    assert _spent(client, h2) == spent
    assert _bills(client, h2)["needs_sync"] is False  # nothing is regrouped or rebuilt afterwards
    assert client.get("/api/budgets", headers=h2).json()  # budgets came across
    assert len(client.get("/api/income", headers=h2).json()) == 1
    assert len(client.get("/api/recurring", headers=h2).json()) == 1


def test_the_two_same_day_same_shop_purchases_stay_separate_and_the_itemised_bill_stays_whole(client, make_user):
    uid, h = make_user()
    _populate(client, h, uid)
    _, h2 = make_user()
    assert _restore(client, h2, _download(client, h)).status_code == 200
    bills = {b["shop"]: b for b in _all_bills(client, h2) if b["shop"] in ("Lidl", "Ikea", "Coop")}
    lidl = [b for b in _all_bills(client, h2) if b["shop"] == "Lidl"]
    assert len(lidl) == 2 and all(b["item_count"] == 1 for b in lidl)
    assert bills["Ikea"]["item_count"] == 3 and D(str(bills["Ikea"]["amount"])) == D("100")
    assert bills["Coop"]["item_count"] == 2  # an auto-grouped bill is restored as it was, to be reviewed


def test_editing_a_restored_single_purchase_updates_its_bill_instead_of_adding_one(client, make_user):
    uid, h = make_user()
    e = _add(client, h, amount="10", shop="Lidl", description="Milk")
    _, h2 = make_user()
    assert _restore(client, h2, _download(client, h)).status_code == 200
    [row] = _expenses(client, h2)
    assert client.put(f"/api/expenses/{row['id']}", json={"shop": "Coop", "amount": "12"}, headers=h2).status_code == 200
    [bill] = _all_bills(client, h2)
    assert bill["shop"] == "Coop" and D(str(bill["amount"])) == D("12") and bill["item_count"] == 1


def test_the_receipt_file_comes_back(client, make_user):
    uid, h = make_user()
    b = _bill(client, h, shop="Phone", amount="45")
    client.post(f"/api/pending-bills/{b['id']}/receipt", files={"file": ("p.pdf", PDF, "application/pdf")}, headers=h)
    _, h2 = make_user()
    assert _restore(client, h2, _download(client, h)).status_code == 200
    [bill] = _all_bills(client, h2)
    r = client.get(f"/api/pending-bills/{bill['id']}/receipt", headers=h2)
    assert r.status_code == 200 and r.content == PDF


def test_only_the_users_own_data_is_in_the_backup(client, make_user):
    uid, h = make_user()
    _add(client, h, amount="10", shop="Mine")
    uid2, other = make_user()
    _add(client, other, amount="99", shop="Theirs")
    z = zipfile.ZipFile(io.BytesIO(_download(client, h)))
    data = json.loads(z.read("backup.json"))
    assert [e["shop"] for e in data["expenses"]] == ["Mine"] and [b["shop"] for b in data["bills"]] == ["Mine"]


def test_restore_refuses_an_account_that_already_has_data(client, make_user):
    uid, h = make_user()
    _add(client, h, amount="10", shop="Lidl")
    data = _download(client, h)
    _, h2 = make_user()
    _add(client, h2, amount="5", shop="Coop")
    r = _restore(client, h2, data)
    assert r.status_code == 409 and "no expenses" in r.json()["detail"]
    assert len(_expenses(client, h2)) == 1  # untouched


def test_restoring_twice_into_the_same_account_is_refused(client, make_user):
    uid, h = make_user()
    _add(client, h, amount="10", shop="Lidl")
    data = _download(client, h)
    _, h2 = make_user()
    assert _restore(client, h2, data).status_code == 200
    assert _restore(client, h2, data).status_code == 409
    assert len(_expenses(client, h2)) == 1


def test_an_empty_account_can_be_backed_up_and_restored(client, make_user):
    _, h = make_user()
    _, h2 = make_user()
    assert _restore(client, h2, _download(client, h)).status_code == 200


def test_rejects_files_that_are_not_backups(client, make_user):
    _, h = make_user()
    assert _restore(client, h, b"hello").status_code == 400
    assert _restore(client, h, _zip({"other.txt": "x"})).status_code == 400
    assert _restore(client, h, _zip({"backup.json": "{not json"})).status_code == 400
    assert _restore(client, h, _zip({"backup.json": {"format": "something-else", "version": 1}})).status_code == 400
    r = _restore(client, h, _zip({"backup.json": {"format": "expense-manager-backup", "version": 99}}))
    assert r.status_code == 400 and "different version" in r.json()["detail"]


def _backup_json(**kw):
    base = {"format": "expense-manager-backup", "version": 1}
    base.update(kw)
    return base


def test_rejects_invalid_values_and_broken_links_without_writing_anything(client, make_user):
    _, h = make_user()
    bad_amount = {"id": 1, "date": "2026-07-01", "category": "Food", "amount": "abc", "currency": "SEK"}
    r = _restore(client, h, _zip({"backup.json": _backup_json(expenses=[bad_amount])}))
    assert r.status_code == 400 and "expenses" in r.json()["detail"]
    dangling = {"id": 1, "date": "2026-07-01", "category": "Food", "amount": "5", "currency": "SEK", "bill": 42}
    assert _restore(client, h, _zip({"backup.json": _backup_json(expenses=[dangling])})).status_code == 400
    bad_currency = {"id": 1, "date": "2026-07-01", "category": "Food", "amount": "5", "currency": "ZZZ"}
    assert _restore(client, h, _zip({"backup.json": _backup_json(expenses=[bad_currency])})).status_code == 400
    huge = {"id": 1, "date": "2026-07-01", "category": "Food", "amount": "1e30", "currency": "SEK"}
    assert _restore(client, h, _zip({"backup.json": _backup_json(expenses=[huge])})).status_code == 400
    assert _expenses(client, h) == []


def test_rejects_a_missing_or_fake_receipt_and_leaves_nothing_behind(client, make_user):
    _, h = make_user()
    bill = {"id": 1, "date": "2026-07-01", "shop": "X", "amount": "5", "status": "pending", "currency": "SEK",
            "receipt": {"file": "receipts/1", "filename": "r.pdf"}}
    assert _restore(client, h, _zip({"backup.json": _backup_json(bills=[bill])})).status_code == 400  # file missing
    r = _restore(client, h, _zip({"backup.json": _backup_json(bills=[bill]), "receipts/1": b"<script>alert(1)</script>"}))
    assert r.status_code == 400 and "PDF, JPEG or PNG" in r.json()["detail"]
    assert _all_bills(client, h) == []


def test_rejects_duplicate_budgets_instead_of_failing_halfway(client, make_user):
    _, h = make_user()
    b = {"category": "Food", "amount": "5", "currency": "SEK"}
    assert _restore(client, h, _zip({"backup.json": _backup_json(budgets=[b, b])})).status_code == 400


def test_backup_and_restore_need_a_login(client):
    assert client.get("/api/backup").status_code in (401, 403)
    assert client.post("/api/backup/restore", files={"file": ("b.zip", b"x", "application/zip")}).status_code in (401, 403)


def _space(client, h, name="Home", **kw):
    r = client.post("/api/groups", json={"name": name, "space_type": "household", **kw}, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_spaces_come_back_with_your_own_entries_and_you_as_the_only_member(client, make_user):
    uid, h = make_user()
    gid = _space(client, h, "Home")
    _add(client, h, amount="10", shop="Mine")
    _add(client, h, amount="50", shop="Shared", group_id=gid)
    other_uid, _other = make_user()
    db = SessionLocal()
    db.add(models.GroupMember(group_id=gid, user_id=other_uid, role="editor"))
    db.add(models.Expense(user_id=other_uid, group_id=gid, date=dt.date(2026, 7, 1), category="Food", amount=99, currency="SEK", shop="Theirs", description=""))
    db.commit()
    db.close()

    data = json.loads(zipfile.ZipFile(io.BytesIO(_download(client, h))).read("backup.json"))
    assert [e["shop"] for e in data["expenses"]] == ["Mine", "Shared"]  # only the user's own entries
    assert data["summary"]["spaces"] == 1 and data["summary"]["others_entries_not_included"] == 1

    uid2, h2 = make_user()
    r = _restore(client, h2, _download(client, h))
    assert r.status_code == 200 and r.json()["spaces"] == 1
    [space] = [g for g in client.get("/api/groups", headers=h2).json() if g["name"] == "Home"]
    assert space["id"] != gid and space["role"] == "owner" and space["member_count"] == 1
    mine = [e for e in _expenses(client, h2) if e["shop"] == "Shared"]
    assert len(mine) == 1 and mine[0]["group_id"] == space["id"]
    assert len(_all_bills(client, h2)) == 2 and _bills(client, h2)["needs_sync"] is False


def test_a_trip_stays_filed_under_its_parent_space(client, make_user):
    uid, h = make_user()
    parent = _space(client, h, "Household")
    db = SessionLocal()
    trip = models.Group(owner_id=uid, name="Goa", space_type="trip", parent_group_id=parent, destination="Goa", currency="SEK", status="Planned")
    db.add(trip)
    db.flush()
    db.add(models.GroupMember(group_id=trip.id, user_id=uid, role="owner"))
    db.commit()
    trip_id = trip.id
    db.close()
    uid2, h2 = make_user()
    assert _restore(client, h2, _download(client, h)).status_code == 200
    db = SessionLocal()
    by_name = {g.name: g for g in db.query(models.Group).filter(models.Group.owner_id == uid2)}
    assert by_name["Goa"].parent_group_id == by_name["Household"].id and by_name["Goa"].destination == "Goa"
    assert by_name["Goa"].id != trip_id
    db.close()


def test_rejects_a_space_that_is_filed_under_itself_or_missing(client, make_user):
    _, h = make_user()
    loop = [{"id": 1, "name": "A", "parent": 2}, {"id": 2, "name": "B", "parent": 1}]
    assert _restore(client, h, _zip({"backup.json": _backup_json(spaces=loop)})).status_code == 400
    missing = [{"id": 1, "name": "A", "parent": 9}]
    assert _restore(client, h, _zip({"backup.json": _backup_json(spaces=missing)})).status_code == 400
    stray = {"id": 1, "date": "2026-07-01", "category": "Food", "amount": "5", "currency": "SEK", "space": 7}
    assert _restore(client, h, _zip({"backup.json": _backup_json(expenses=[stray])})).status_code == 400
    assert client.get("/api/groups", headers=h).json() == []
