"""Re-itemising: edit an itemised bill's items, or turn it back into a single total."""
import datetime as dt
from decimal import Decimal

from app.db import models
from app.db.database import SessionLocal
from tests.test_bills_workflow import TODAY, _bill, _bills, _expenses, _items, _setting, _spent

D = Decimal


def _itemised(client, h, amount="100", items=(60, 30, 10), shop="Lidl"):
    """A bill (auto-recorded as a total) that has been itemised."""
    b = _bill(client, h, shop=shop, amount=amount)
    r = client.post("/api/expenses/bulk", json={"items": _items(*items, shop=shop), "bill_id": b["id"]}, headers=h)
    assert r.status_code == 201, r.text
    return b


def _linked(client, h, bill_id):
    return [e for e in _expenses(client, h) if e["source_bill_id"] == bill_id]


# ── reading a bill and its items ─────────────────────────────────────────
def test_get_bill_and_its_items(client, make_user):
    _, h = make_user()
    b = _itemised(client, h)
    got = client.get(f"/api/bills/{b['id']}", headers=h).json()
    assert got["status"] == "itemised" and got["item_count"] == 3 and got["shop"] == "Lidl"
    items = client.get(f"/api/bills/{b['id']}/items", headers=h).json()
    assert [D(str(i["amount"])) for i in items] == [D("60"), D("30"), D("10")]
    assert all(i["source_bill_id"] == b["id"] and i["bill_total_only"] is False for i in items)


def test_a_total_only_bill_has_no_items(client, make_user):
    _, h = make_user()
    b = _bill(client, h)  # auto-recorded as a total
    assert client.get(f"/api/bills/{b['id']}/items", headers=h).json() == []  # its one line is the total, not an item


def test_other_users_cannot_read_a_bill_or_its_items(client, make_user):
    _, a = make_user()
    _, other = make_user()
    b = _itemised(client, a)
    assert client.get(f"/api/bills/{b['id']}", headers=other).status_code == 404
    assert client.get(f"/api/bills/{b['id']}/items", headers=other).status_code == 404


# ── editing the items (re-itemise) ───────────────────────────────────────
def test_reitemising_replaces_the_old_items(client, make_user):
    _, h = make_user()
    b = _itemised(client, h, amount="100", items=(60, 30, 10))
    assert _spent(client, h) == D("100")
    r = client.post("/api/expenses/bulk", json={"items": _items(70, 25, shop="Lidl"), "bill_id": b["id"], "replace": True}, headers=h)
    assert r.status_code == 201, r.text
    rows = _linked(client, h, b["id"])
    assert sorted(D(str(e["amount"])) for e in rows) == [D("25"), D("70")]  # the old three are gone
    assert len(_expenses(client, h)) == 2  # nothing left over
    assert _spent(client, h) == D("95")  # replaced, not added to
    bill = client.get(f"/api/bills/{b['id']}", headers=h).json()
    assert bill["status"] == "itemised" and bill["item_count"] == 2


def test_an_itemised_bill_is_refused_without_the_replace_flag(client, make_user):
    """A double-clicked or repeated submit must not silently duplicate or wipe items."""
    _, h = make_user()
    b = _itemised(client, h)
    r = client.post("/api/expenses/bulk", json={"items": _items(100, shop="Lidl"), "bill_id": b["id"]}, headers=h)
    assert r.status_code == 409
    assert sorted(D(str(e["amount"])) for e in _linked(client, h, b["id"])) == [D("10"), D("30"), D("60")]  # untouched


def test_replace_also_works_for_a_bill_that_is_not_itemised_yet(client, make_user):
    _, h = make_user()
    b = _bill(client, h, amount="50")
    r = client.post("/api/expenses/bulk", json={"items": _items(30, 20), "bill_id": b["id"], "replace": True}, headers=h)
    assert r.status_code == 201 and _spent(client, h) == D("50")
    assert [e["bill_total_only"] for e in _expenses(client, h)] == [False, False]  # the total line was replaced too


def test_a_failed_reitemise_leaves_the_existing_items_alone(client, make_user):
    _, a = make_user()
    _, stranger = make_user()
    group = client.post("/api/groups", json={"name": "Not mine"}, headers=stranger).json()
    b = _itemised(client, a)
    bad = _items(70, 30, shop="Lidl")
    bad[1]["group_id"] = group["id"]  # a space this user is not in
    r = client.post("/api/expenses/bulk", json={"items": bad, "bill_id": b["id"], "replace": True}, headers=a)
    assert r.status_code == 403
    assert sorted(D(str(e["amount"])) for e in _linked(client, a, b["id"])) == [D("10"), D("30"), D("60")]
    invalid = client.post("/api/expenses/bulk", json={"items": [{"date": TODAY, "category": "F", "amount": "5", "currency": "XXX"}], "bill_id": b["id"], "replace": True}, headers=a)
    assert invalid.status_code == 422
    assert len(_linked(client, a, b["id"])) == 3 and _spent(client, a) == D("100")


def test_replace_only_touches_the_users_own_expenses(client, make_user):
    uid_a, a = make_user()
    uid_b, _ = make_user()
    b = _itemised(client, a)
    db = SessionLocal()
    db.add(models.Expense(user_id=uid_b, date=dt.date.today(), category="Food", description="someone else's", amount=7, currency="SEK", source_bill_id=b["id"]))
    db.commit()
    db.close()
    client.post("/api/expenses/bulk", json={"items": _items(100, shop="Lidl"), "bill_id": b["id"], "replace": True}, headers=a)
    db = SessionLocal()
    survivor = db.query(models.Expense).filter(models.Expense.user_id == uid_b).count()
    db.close()
    assert survivor == 1


def test_reitemising_someone_elses_bill_is_a_404(client, make_user):
    _, a = make_user()
    _, other = make_user()
    b = _itemised(client, a)
    r = client.post("/api/expenses/bulk", json={"items": _items(5), "bill_id": b["id"], "replace": True}, headers=other)
    assert r.status_code == 404
    assert len(_linked(client, a, b["id"])) == 3


def test_it_can_be_reitemised_repeatedly(client, make_user):
    _, h = make_user()
    b = _itemised(client, h, amount="100", items=(100,))
    for amounts in [(50, 50), (40, 30, 30), (100,)]:
        r = client.post("/api/expenses/bulk", json={"items": _items(*amounts, shop="Lidl"), "bill_id": b["id"], "replace": True}, headers=h)
        assert r.status_code == 201
        assert len(_linked(client, h, b["id"])) == len(amounts) and _spent(client, h) == D("100")


# ── turning it back into a total ─────────────────────────────────────────
def test_revert_replaces_the_items_with_one_total_line(client, make_user):
    _, h = make_user()
    b = _itemised(client, h, amount="100", items=(60, 30))  # items add up to 90, the bill is 100
    assert _spent(client, h) == D("90")
    r = client.post(f"/api/bills/{b['id']}/revert-to-total", json={"category": "Groceries"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "total_only" and r.json()["item_count"] == 1
    [line] = _linked(client, h, b["id"])
    assert (D(str(line["amount"])), line["category"], line["bill_total_only"], line["description"]) == (D("100"), "Groceries", True, "Lidl")
    assert len(_expenses(client, h)) == 1 and _spent(client, h) == D("100")  # back to the bill's own total


def test_revert_defaults_to_the_bills_category(client, make_user):
    _, h = make_user()
    b = _itemised(client, h)
    client.post(f"/api/bills/{b['id']}/revert-to-total", headers=h)
    assert _linked(client, h, b["id"])[0]["category"] == "Bills"


def test_revert_then_itemise_again_round_trips(client, make_user):
    _, h = make_user()
    b = _itemised(client, h, amount="100", items=(60, 40))
    client.post(f"/api/bills/{b['id']}/revert-to-total", headers=h)
    assert client.post("/api/expenses/bulk", json={"items": _items(55, 45, shop="Lidl"), "bill_id": b["id"]}, headers=h).status_code == 201
    assert _bills(client, h, status="itemised")["items"][0]["item_count"] == 2 and _spent(client, h) == D("100")


def test_only_an_itemised_bill_can_be_reverted(client, make_user):
    _, h = make_user()
    _setting(client, h, False)
    pending = _bill(client, h, shop="P")
    assert client.post(f"/api/bills/{pending['id']}/revert-to-total", headers=h).status_code == 409
    client.post(f"/api/bills/{pending['id']}/record-total", headers=h)
    assert client.post(f"/api/bills/{pending['id']}/revert-to-total", headers=h).status_code == 409  # total_only
    assert _spent(client, h) == D("35.91")  # nothing changed


def test_a_second_revert_is_refused_and_creates_no_duplicate(client, make_user):
    _, h = make_user()
    b = _itemised(client, h)
    assert client.post(f"/api/bills/{b['id']}/revert-to-total", headers=h).status_code == 200
    assert client.post(f"/api/bills/{b['id']}/revert-to-total", headers=h).status_code == 409
    assert len(_linked(client, h, b["id"])) == 1


def test_revert_needs_a_bill_amount(client, make_user):
    uid, h = make_user()
    b = _itemised(client, h)
    db = SessionLocal()
    db.query(models.PendingBill).filter(models.PendingBill.id == b["id"]).update({"amount": 0})
    db.commit()
    db.close()
    r = client.post(f"/api/bills/{b['id']}/revert-to-total", headers=h)
    assert r.status_code == 400 and len(_linked(client, h, b["id"])) == 3  # items kept


def test_revert_on_someone_elses_bill_is_a_404(client, make_user):
    _, a = make_user()
    _, other = make_user()
    b = _itemised(client, a)
    assert client.post(f"/api/bills/{b['id']}/revert-to-total", headers=other).status_code == 404
    assert len(_linked(client, a, b["id"])) == 3


def test_rejects_an_invalid_category_length_and_amount_cap(client, make_user):
    _, h = make_user()
    b = _itemised(client, h)
    assert client.post(f"/api/bills/{b['id']}/revert-to-total", json={"category": "x" * 101}, headers=h).status_code == 422
