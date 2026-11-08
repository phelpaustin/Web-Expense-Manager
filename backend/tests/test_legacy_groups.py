"""Review of purchases an older version grouped by date and shop: list, keep, split."""
from decimal import Decimal

from tests.test_bill_sync import (
    JULY, PDF, _add, _all_bills, _bill_of, _insert, _legacy_bill, _sync,
)

D = Decimal


def _groups(client, h):
    r = client.get("/api/bills/legacy-groups", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _resolve(client, h, action, ids):
    return client.post("/api/bills/legacy-groups/resolve", json={"action": action, "ids": ids}, headers=h)


def _setup(uid):
    ids = _insert(uid, [{"shop": "Lidl", "amount": 10, "description": "Milk"}, {"shop": "Lidl", "amount": 5, "description": "Eggs"}])
    return _legacy_bill(uid, ids), ids


def test_lists_auto_grouped_bills_with_their_items(client, make_user):
    uid, h = make_user()
    bill_id, ids = _setup(uid)
    [g] = _groups(client, h)
    assert g["id"] == bill_id and g["shop"] == "Lidl" and D(str(g["amount"])) == D("15")
    assert [i["id"] for i in g["items"]] == ids and [i["description"] for i in g["items"]] == ["Milk", "Eggs"]


def test_a_single_item_legacy_bill_and_user_made_bills_are_not_listed(client, make_user):
    uid, h = make_user()
    one = _insert(uid, [{"shop": "Coop", "amount": 4}])
    _legacy_bill(uid, one, shop="Coop")
    _add(client, h, amount="3", shop="ICA")  # an ordinary purchase (own key)
    assert _groups(client, h) == []


def test_nothing_is_listed_for_other_users(client, make_user):
    uid, _ = make_user()
    _setup(uid)
    _, other = make_user()
    assert _groups(client, other) == []


def test_keep_makes_it_a_real_bill_that_is_never_regrouped(client, make_user):
    uid, h = make_user()
    bill_id, ids = _setup(uid)
    assert _resolve(client, h, "keep", [bill_id]).json() == {"changed": 1}
    assert _groups(client, h) == []
    # Change one item's shop: an explicit bill keeps its items together.
    client.put(f"/api/expenses/{ids[0]}", json={"shop": "Coop"}, headers=h)
    _sync(client, h)
    [bill] = _all_bills(client, h)
    assert bill["id"] == bill_id and bill["item_count"] == 2 and D(str(bill["amount"])) == D("15")


def test_split_makes_one_purchase_per_expense(client, make_user):
    uid, h = make_user()
    bill_id, ids = _setup(uid)
    assert _resolve(client, h, "split", [bill_id]).json() == {"changed": 1}
    assert _groups(client, h) == []
    bills = _all_bills(client, h)
    assert len(bills) == 2 and all(b["item_count"] == 1 for b in bills)
    assert sorted(D(str(b["amount"])) for b in bills) == [D("5"), D("10")]
    assert _bill_of(client, h, ids[0])["id"] != _bill_of(client, h, ids[1])["id"]


def test_split_keeps_a_bill_that_has_a_receipt_so_the_file_is_not_lost(client, make_user):
    uid, h = make_user()
    bill_id, ids = _setup(uid)
    assert client.post(f"/api/pending-bills/{bill_id}/receipt", files={"file": ("r.pdf", PDF, "application/pdf")}, headers=h).status_code == 200
    assert _resolve(client, h, "split", [bill_id]).json() == {"changed": 1}
    bills = {b["id"]: b for b in _all_bills(client, h)}
    assert bills[bill_id]["status"] == "pending" and bills[bill_id]["has_receipt"] is True
    assert sum(1 for b in bills.values() if b["status"] == "itemised") == 2


def test_resolve_ignores_bills_that_are_not_legacy_groups(client, make_user):
    uid, h = make_user()
    e = _add(client, h, amount="3", shop="ICA")
    own = _bill_of(client, h, e["id"])["id"]
    assert _resolve(client, h, "split", [own]).json() == {"changed": 0}
    assert _resolve(client, h, "keep", [own]).json() == {"changed": 0}
    assert _bill_of(client, h, e["id"])["id"] == own


def test_resolve_cannot_touch_another_users_bill(client, make_user):
    uid, owner = make_user()
    bill_id, _ids = _setup(uid)
    _, other = make_user()
    assert _resolve(client, other, "split", [bill_id]).json() == {"changed": 0}
    assert len(_groups(client, owner)) == 1


def test_resolve_validates_input(client, make_user):
    _, h = make_user()
    assert _resolve(client, h, "delete", [1]).status_code == 422
    assert _resolve(client, h, "split", []).status_code == 422
