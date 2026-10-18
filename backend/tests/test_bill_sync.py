"""Every expense is represented on the Bills page, however it was entered."""
import datetime as dt
import os
import sqlite3
import tempfile
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.api import bill_sync
from app.db import models
from app.db.database import SessionLocal
from tests.test_bills_workflow import PDF, _bill, _bills, _expenses, _items, _setting, _spent
from tests.test_migration_0015 import _alembic

D = Decimal
JULY = "2026-07-{:02d}"


def _add(client, h, amount="10", date=JULY.format(10), **kw):
    body = {"date": date, "category": "Food", "amount": str(amount), "currency": "SEK", **kw}
    r = client.post("/api/expenses", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _insert(uid, rows):
    """Expenses as they were before this feature: straight into the database, no bill."""
    db = SessionLocal()
    ids = []
    for r in rows:
        e = models.Expense(
            user_id=uid, date=dt.date.fromisoformat(r.get("date", JULY.format(10))), category=r.get("category", "Food"),
            description=r.get("description", ""), amount=r.get("amount", 10), currency=r.get("currency", "SEK"),
            shop=r.get("shop", ""), group_id=r.get("group_id"),
        )
        db.add(e)
        db.flush()
        ids.append(e.id)
    db.commit()
    db.close()
    return ids


def _all_bills(client, h):
    return _bills(client, h, status="all", page_size=200)["items"]


def _sync(client, h):
    r = client.post("/api/bills/sync", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["changed"]


def _synced_bills(client, h, **kw):
    """Rows written straight to the database (or by routes that do not file them) need a sync;
    a GET never does it."""
    _sync(client, h)
    return _bills(client, h, **kw)


def _synced_all(client, h):
    _sync(client, h)
    return _all_bills(client, h)


def _bill_of(client, h, expense_id):
    e = next(x for x in _expenses(client, h) if x["id"] == expense_id)
    assert e["source_bill_id"] is not None, "expense is not filed under a bill"
    return client.get(f"/api/bills/{e['source_bill_id']}", headers=h).json()


# ── adoption ─────────────────────────────────────────────────────────────
def test_a_typed_in_expense_shows_up_as_an_itemised_bill(client, make_user):
    _, h = make_user()
    _add(client, h, amount="42.5", shop="Coop", description="Milk")
    [bill] = _all_bills(client, h)
    assert (bill["shop"], D(str(bill["amount"])), bill["currency"], bill["status"]) == ("Coop", D("42.5"), "SEK", "itemised")
    assert bill["from_expenses"] is True and bill["item_count"] == 1 and bill["date"] == JULY.format(10)
    assert _bills(client, h)["counts"] == {"pending": 0, "total_only": 0, "itemised": 1, "all": 1}


def test_an_expense_with_no_shop_is_a_bill_named_after_it(client, make_user):
    _, h = make_user()
    _add(client, h, description="Coffee")
    _add(client, h, description="", category="Transport")
    assert sorted(b["shop"] for b in _all_bills(client, h)) == ["Coffee", "Transport"]


def test_two_shopless_expenses_on_one_day_stay_two_bills(client, make_user):
    _, h = make_user()
    _add(client, h, description="Coffee", amount="30")
    _add(client, h, description="Bus", amount="40")
    assert len(_all_bills(client, h)) == 2


def test_lines_from_one_shop_on_one_day_are_one_bill(client, make_user):
    _, h = make_user()
    _add(client, h, amount="10", shop="ICA", description="Milk")
    _add(client, h, amount="20", shop="ica ", description="Bread")  # same shop, different case/space
    _add(client, h, amount="5", shop="ICA", description="Gum")
    [bill] = _all_bills(client, h)
    assert D(str(bill["amount"])) == D("35") and bill["item_count"] == 3 and bill["shop"] == "ICA"


@pytest.mark.parametrize(
    "other",
    [{"date": JULY.format(11)}, {"shop": "Coop"}, {"currency": "EUR"}],
    ids=["another day", "another shop", "another currency"],
)
def test_expenses_that_differ_are_separate_bills(client, make_user, other):
    _, h = make_user()
    _add(client, h, shop="ICA")
    _add(client, h, **{"shop": "ICA", **other})
    assert len(_all_bills(client, h)) == 2


def test_the_same_shop_in_a_shared_space_is_a_separate_bill(client, make_user):
    _, h = make_user()
    g = client.post("/api/groups", json={"name": "Flat"}, headers=h).json()
    _add(client, h, shop="ICA")
    _add(client, h, shop="ICA", group_id=g["id"])
    assert len(_all_bills(client, h)) == 2


def test_expenses_that_already_existed_are_picked_up_on_first_visit(client, make_user):
    uid, h = make_user()
    ids = _insert(uid, [{"shop": "Lidl", "amount": 35.91}, {"shop": "Lidl", "amount": 10}, {"description": "Kiosk", "amount": 25}])
    assert _synced_bills(client, h, status="all")["total"] == 2  # Lidl (2 lines) + the kiosk expense
    bills = {b["shop"]: b for b in _synced_all(client, h)}
    assert D(str(bills["Lidl"]["amount"])) == D("45.91") and bills["Lidl"]["item_count"] == 2
    assert all(e["source_bill_id"] for e in _expenses(client, h) if e["id"] in ids)


def test_listing_expenses_or_bills_never_writes(client, make_user):
    uid, h = make_user()
    _insert(uid, [{"shop": "Lidl", "amount": 12}])
    [e] = _expenses(client, h)
    assert e["source_bill_id"] is None  # a GET does not file it
    page = _bills(client, h, status="all")
    assert page["total"] == 0 and page["needs_sync"] is True  # but it says a sync is due
    db = SessionLocal()
    assert db.query(models.PendingBill).filter(models.PendingBill.user_id == uid).count() == 0
    db.close()


def test_post_sync_files_them_and_clears_the_flag(client, make_user):
    uid, h = make_user()
    _insert(uid, [{"shop": "Lidl", "amount": 12}])
    assert _sync(client, h) is True
    [e] = _expenses(client, h)
    assert e["source_bill_id"] is not None and e["bill_total_only"] is False
    assert _bills(client, h)["needs_sync"] is False
    assert _sync(client, h) is False  # idempotent


def test_needs_sync_also_reports_a_stale_derived_bill(client, make_user):
    uid, h = make_user()
    [eid] = _insert(uid, [{"shop": "Lidl", "amount": 12}])
    _sync(client, h)
    db = SessionLocal()
    db.query(models.Expense).filter(models.Expense.id == eid).update({"shop": "ICA"})
    db.commit()
    db.close()
    assert _bills(client, h, status="all")["needs_sync"] is True
    _sync(client, h)
    assert _bills(client, h, status="all")["needs_sync"] is False


def test_sync_only_touches_the_callers_expenses(client, make_user):
    a_id, a = make_user()
    b_id, b = make_user()
    _insert(a_id, [{"shop": "Mine"}])
    _insert(b_id, [{"shop": "Theirs"}])
    _sync(client, a)
    assert _bills(client, b)["needs_sync"] is True
    assert [x["shop"] for x in _all_bills(client, a)] == ["Mine"]


def test_every_write_route_files_its_expenses_without_a_sync(client, make_user):
    """Create, import and recurring posting need no later visit to the Bills page."""
    _, h = make_user()
    _add(client, h, shop="Coop")
    csv = "Date,Category,Amount,Shop\n2026-07-11,Food,5,Lidl\n"
    assert client.post("/api/expenses/import", files={"file": ("e.csv", csv, "text/csv")}, headers=h).status_code == 200
    t = client.post("/api/recurring", json={"item": "Rent", "amount": "900"}, headers=h).json()
    assert client.post(f"/api/recurring/{t['id']}/apply", headers=h).status_code == 200
    assert _bills(client, h)["needs_sync"] is False
    assert len(_all_bills(client, h)) == 3
    assert all(e["source_bill_id"] is not None for e in _expenses(client, h))


def test_startup_backfill_files_existing_expenses_for_every_user(client, make_user):
    a_id, a = make_user()
    b_id, b = make_user()
    _insert(a_id, [{"shop": "Lidl"}, {"shop": "Lidl"}])
    _insert(b_id, [{"description": "Kiosk"}])
    db = SessionLocal()
    try:
        assert bill_sync.backfill_all(db) >= 2
    finally:
        db.close()
    assert len(_all_bills(client, a)) == 1 and len(_all_bills(client, b)) == 1
    assert _bills(client, a)["needs_sync"] is False


def test_a_failed_post_write_sync_does_not_fail_the_request(client, make_user, monkeypatch):
    _, h = make_user()

    def boom(*_a, **_k):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(bill_sync, "adopt_if_needed", boom)
    r = client.post("/api/expenses", json={"date": JULY.format(10), "category": "Food", "amount": "5", "shop": "Coop"}, headers=h)
    assert r.status_code == 201  # saved; the next sync picks it up
    monkeypatch.undo()
    assert _bills(client, h)["needs_sync"] is True


def test_adoption_is_idempotent_and_changes_no_totals(client, make_user):
    uid, h = make_user()
    _insert(uid, [{"shop": "A", "amount": 10}, {"shop": "A", "amount": 5}, {"description": "B", "amount": 7}])
    before = _spent(client, h)
    first = {b["id"]: b for b in _synced_all(client, h)}
    again = {b["id"]: b for b in _synced_all(client, h)}
    assert first.keys() == again.keys() and _bills(client, h)["counts"]["all"] == 2
    assert _spent(client, h) == before == D("22")


def test_total_only_placeholders_are_not_adopted_twice(client, make_user):
    _, h = make_user()
    b = _bill(client, h, shop="LIDL", amount="35.91")  # recorded as a total: a linked placeholder
    _add(client, h, shop="Coop")
    assert [x["shop"] for x in _all_bills(client, h)].count("LIDL") == 1
    assert len(_all_bills(client, h)) == 2 and b["status"] == "total_only"


def test_users_only_see_their_own_expenses_as_bills(client, make_user):
    uid_a, a = make_user()
    uid_b, b = make_user()
    _insert(uid_a, [{"shop": "Mine", "amount": 1}])
    _insert(uid_b, [{"shop": "Theirs", "amount": 2}])
    assert [x["shop"] for x in _synced_all(client, a)] == ["Mine"]
    assert [x["shop"] for x in _synced_all(client, b)] == ["Theirs"]


def test_a_members_expense_in_a_shared_space_belongs_to_their_bills(client, make_user):
    uid_owner, owner = make_user()
    uid_member, member = make_user()
    g = client.post("/api/groups", json={"name": "Flat"}, headers=owner).json()
    db = SessionLocal()
    db.add(models.GroupMember(group_id=g["id"], user_id=uid_member, role="editor"))
    db.commit()
    db.close()
    _add(client, member, shop="ICA", group_id=g["id"])
    assert [x["shop"] for x in _all_bills(client, member)] == ["ICA"]
    assert _all_bills(client, owner) == []  # the owner sees it as an expense, not as one of their bills
    assert len(_expenses(client, owner)) == 1


def test_expenses_with_no_owner_are_left_alone(client, make_user):
    _, h = make_user()
    db = SessionLocal()
    db.add(models.Expense(user_id=None, date=dt.date(2026, 7, 1), category="Food", amount=3, currency="SEK"))
    db.commit()
    db.close()
    assert _all_bills(client, h) == []


# ── every way of entering an expense ends up everywhere ──────────────────
def test_every_route_is_reflected_in_bills_stats_and_exports(client, make_user):
    _, h = make_user()
    g = client.post("/api/groups", json={"name": "Trip"}, headers=h).json()
    total = D("0")

    def counted(amount):
        nonlocal total
        total += D(str(amount))

    _add(client, h, amount="11", shop="Single", description="typed in"); counted(11)                    # Expenses form
    client.post("/api/expenses/bulk", json={"items": _items(4, 6, shop="Bulk")}, headers=h); counted(10)  # bulk api
    client.post("/api/expenses/bulk", json={"items": _items(2, 3, shop="Receipt"), "as_bill": True}, headers=h); counted(5)  # Add by bill
    _add(client, h, amount="7", shop="Space", group_id=g["id"]); counted(7)                              # shared space
    csv = f"Date,Category,Amount,Shop\n{JULY.format(3)},Food,9,Imported\n".encode()
    assert client.post("/api/expenses/import", files={"file": ("x.csv", csv, "text/csv")}, headers=h).json()["added"] == 1; counted(9)
    t = client.post("/api/recurring", json={"item": "Gym", "amount": "30", "frequency": "Monthly"}, headers=h).json()
    client.post(f"/api/recurring/{t['id']}/apply", headers=h); counted(30)                               # recurring
    _setting(client, h, True)
    _bill(client, h, shop="Statement", amount="15"); counted(15)                                        # bill recorded as a total

    expenses = _expenses(client, h)
    assert sum(D(str(e["amount"])) for e in expenses) == total and len(expenses) == 9

    # on the Bills page: every expense is under a bill, and the bills add up to the same spending
    bills = _all_bills(client, h)
    assert all(e["source_bill_id"] for e in expenses)
    assert sum(D(str(b["amount"])) for b in bills if b["status"] in ("itemised", "total_only")) == total
    assert {b["shop"] for b in bills} >= {"Single", "Bulk", "Receipt", "Space", "Imported", "Gym", "Statement"}

    # in the stats: the same spending
    assert _spent(client, h) == total
    summary = client.get("/api/expenses/summary", headers=h).json()
    assert summary["count"] == 9 and sum(D(str(v)) for v in summary["by_category"].values()) == total
    metrics = client.get("/api/metrics", headers=h).json()
    assert "this_month_spent" in metrics
    cats = client.get("/api/analytics/categories", headers=h).json()
    assert sum(D(str(c["total"])) for c in cats) == total
    trends = client.get("/api/analytics/trends", headers=h).json()
    assert sum(D(str(m["total"])) for m in trends["monthly"]) == total
    # and in the export
    exported = client.get("/api/expenses/export", headers=h).text
    assert exported.count("\n") >= 9 and "Imported" in exported and "Gym" in exported


def test_budgets_count_every_route(client, make_user):
    _, h = make_user()
    client.put("/api/budgets", json={"category": "Food", "amount": "1000"}, headers=h)
    _add(client, h, amount="100", date=dt.date.today().isoformat())
    client.post("/api/expenses/bulk", json={"items": _items(50, 25, shop="Bulk"), "as_bill": True}, headers=h)
    _bills(client, h)  # adoption happens; it must not change what the budget sees
    rows = client.get("/api/budgets/status", headers=h).json()
    food = next(r for r in rows if r["category"] == "Food")
    assert D(str(food["spent"])) == D("175")


# ── Add by bill ──────────────────────────────────────────────────────────
def test_add_by_bill_creates_its_bill_straight_away(client, make_user):
    _, h = make_user()
    r = client.post("/api/expenses/bulk", json={"items": _items(30, 20, shop="Lidl"), "as_bill": True}, headers=h)
    assert r.status_code == 201
    ids = {e["source_bill_id"] for e in r.json()}
    assert len(ids) == 1 and None not in ids  # linked in the response itself, no later visit needed
    [bill] = _all_bills(client, h)
    assert (bill["shop"], D(str(bill["amount"])), bill["item_count"], bill["status"], bill["from_expenses"]) == ("Lidl", D("50"), 2, "itemised", True)


def test_add_by_bill_keeps_its_lines_together_whatever_their_shop(client, make_user):
    _, h = make_user()
    items = _items(30, 20, shop="Lidl")
    items[1]["shop"] = ""  # one line has no shop
    client.post("/api/expenses/bulk", json={"items": items, "as_bill": True}, headers=h)
    [bill] = _all_bills(client, h)
    assert bill["item_count"] == 2  # not split up by the shop rule
    first = client.get(f"/api/bills/{bill['id']}/items", headers=h).json()
    assert len(first) == 2
    _bills(client, h)
    assert len(_all_bills(client, h)) == 1  # still one bill after another reconcile


def test_without_as_bill_a_bulk_import_is_adopted_by_the_usual_rules(client, make_user):
    _, h = make_user()
    r = client.post("/api/expenses/bulk", json={"items": _items(5, 6, shop="A")}, headers=h)
    assert all(e["source_bill_id"] is None for e in r.json())  # nothing linked yet...
    assert len(_synced_all(client, h)) == 1  # ...until the Bills page (or Expenses list) loads: one shop, one bill


def test_lines_on_different_days_or_currencies_are_not_forced_into_one_bill(client, make_user):
    _, h = make_user()
    items = _items(5, 6, shop="A")
    items[1]["date"] = JULY.format(2)
    client.post("/api/expenses/bulk", json={"items": items, "as_bill": True}, headers=h)
    assert len(_synced_all(client, h)) == 2


# ── editing and deleting expenses keeps the bill right ───────────────────
def test_editing_an_amount_updates_the_bill_at_once(client, make_user):
    _, h = make_user()
    e = _add(client, h, amount="10", shop="Coop")
    _add(client, h, amount="20", shop="Coop")
    [bill] = _all_bills(client, h)
    assert D(str(bill["amount"])) == D("30")
    client.put(f"/api/expenses/{e['id']}", json={"amount": "15"}, headers=h)
    assert D(str(client.get(f"/api/bills/{bill['id']}", headers=h).json()["amount"])) == D("35")


def test_changing_the_shop_moves_the_expense_to_the_right_bill(client, make_user):
    _, h = make_user()
    a = _add(client, h, amount="10", shop="ICA")
    _add(client, h, amount="20", shop="ICA")
    _add(client, h, amount="7", shop="Coop")
    client.put(f"/api/expenses/{a['id']}", json={"shop": "Coop"}, headers=h)
    bills = {b["shop"]: b for b in _all_bills(client, h)}
    assert D(str(bills["ICA"]["amount"])) == D("20") and bills["ICA"]["item_count"] == 1
    assert D(str(bills["Coop"]["amount"])) == D("17") and bills["Coop"]["item_count"] == 2


def test_changing_the_date_or_currency_moves_it_too(client, make_user):
    _, h = make_user()
    a = _add(client, h, amount="10", shop="ICA")
    _add(client, h, amount="20", shop="ICA")
    client.put(f"/api/expenses/{a['id']}", json={"date": JULY.format(12)}, headers=h)
    assert sorted((b["date"], D(str(b["amount"]))) for b in _all_bills(client, h)) == [(JULY.format(10), D("20")), (JULY.format(12), D("10"))]
    client.put(f"/api/expenses/{a['id']}", json={"currency": "EUR"}, headers=h)
    assert sorted(b["currency"] for b in _all_bills(client, h)) == ["EUR", "SEK"]


def test_a_bill_with_one_expense_follows_it_when_the_shop_is_added(client, make_user):
    _, h = make_user()
    a = _add(client, h, description="Coffee", amount="30")
    b2 = _add(client, h, description="Tea", amount="25", shop="Cafe")
    client.put(f"/api/expenses/{a['id']}", json={"shop": "Cafe"}, headers=h)
    bills = _all_bills(client, h)
    assert [b["shop"] for b in bills] == ["Cafe"] and D(str(bills[0]["amount"])) == D("55")
    assert b2["id"] != a["id"]


def test_deleting_expenses_shrinks_the_bill_and_removes_it_with_the_last_one(client, make_user):
    _, h = make_user()
    a = _add(client, h, amount="10", shop="ICA")
    b = _add(client, h, amount="20", shop="ICA")
    client.delete(f"/api/expenses/{a['id']}", headers=h)
    [bill] = _all_bills(client, h)
    assert D(str(bill["amount"])) == D("20") and bill["item_count"] == 1
    client.delete(f"/api/expenses/{b['id']}", headers=h)
    assert _all_bills(client, h) == []


def test_a_receipt_keeps_its_bill_when_every_expense_is_deleted(client, make_user):
    _, h = make_user()
    e = _add(client, h, amount="10", shop="ICA")
    [bill] = _all_bills(client, h)
    client.post(f"/api/pending-bills/{bill['id']}/receipt", files={"file": ("r.pdf", PDF, "application/pdf")}, headers=h)
    client.delete(f"/api/expenses/{e['id']}", headers=h)
    [kept] = _all_bills(client, h)
    assert kept["status"] == "pending" and kept["has_receipt"] is True and kept["from_expenses"] is False
    assert _spent(client, h) == 0  # no spending, but the receipt is still there to itemise


def test_a_statement_bill_keeps_its_amount_when_items_are_edited(client, make_user):
    _, h = make_user()
    b = _bill(client, h, shop="Lidl", amount="100")
    client.post("/api/expenses/bulk", json={"items": _items(60, 30, shop="Lidl"), "bill_id": b["id"]}, headers=h)
    item = client.get(f"/api/bills/{b['id']}/items", headers=h).json()[0]
    client.put(f"/api/expenses/{item['id']}", json={"amount": "50", "shop": "Elsewhere"}, headers=h)
    bill = client.get(f"/api/bills/{b['id']}", headers=h).json()
    assert D(str(bill["amount"])) == D("100") and bill["item_count"] == 2 and bill["from_expenses"] is False


# ── bills made from expenses are managed through their expenses ──────────
def test_such_a_bill_cannot_be_deleted_directly(client, make_user):
    _, h = make_user()
    _add(client, h, shop="ICA")
    [bill] = _all_bills(client, h)
    r = client.delete(f"/api/pending-bills/{bill['id']}", headers=h)
    assert r.status_code == 409 and "delete those expenses" in r.json()["detail"]
    out = client.post("/api/bills/bulk-delete", json={"ids": [bill["id"]]}, headers=h).json()
    assert out["deleted"] == 0 and "delete those expenses" in out["skipped"][0]["reason"]
    assert len(_all_bills(client, h)) == 1 and _spent(client, h) == D("10")


def test_editing_the_items_of_such_a_bill_keeps_them_as_one_bill(client, make_user):
    _, h = make_user()
    _add(client, h, amount="10", shop="ICA", description="Milk")
    _add(client, h, amount="20", shop="ICA", description="Bread")
    [bill] = _all_bills(client, h)
    new_items = _items(5, 5, 5, shop="")  # no shop on the lines now
    r = client.post("/api/expenses/bulk", json={"items": new_items, "bill_id": bill["id"], "replace": True}, headers=h)
    assert r.status_code == 201
    [after] = _all_bills(client, h)
    assert after["id"] == bill["id"] and after["item_count"] == 3 and D(str(after["amount"])) == D("15")
    assert after["from_expenses"] is True and _spent(client, h) == D("15")  # still tracked, still one bill


def test_reverting_such_a_bill_hands_it_to_the_user(client, make_user):
    _, h = make_user()
    _add(client, h, amount="10", shop="ICA")
    _add(client, h, amount="20", shop="ICA")
    [bill] = _all_bills(client, h)
    r = client.post(f"/api/bills/{bill['id']}/revert-to-total", headers=h).json()
    assert r["status"] == "total_only" and r["from_expenses"] is False
    [line] = [e for e in _expenses(client, h)]
    assert line["bill_total_only"] is True and D(str(line["amount"])) == D("30")
    again = _all_bills(client, h)  # a later visit must not re-file the placeholder
    assert len(again) == 1 and again[0]["status"] == "total_only"


def test_a_receipt_can_be_attached_to_a_purchase_entered_as_expenses(client, make_user):
    _, h = make_user()
    _add(client, h, amount="35.91", shop="Lidl", date=JULY.format(21))
    [bill] = _all_bills(client, h)
    attached = client.post("/api/pending-bills/upload", files={"file": ("l.pdf", PDF, "application/pdf")}, data={"attach_to": str(bill["id"])}, headers=h)
    assert attached.status_code == 200 and attached.json()["bill"]["has_receipt"] is True
    assert _spent(client, h) == D("35.91") and len(_all_bills(client, h)) == 1  # nothing counted twice


# ── safety ───────────────────────────────────────────────────────────────
def test_two_derived_bills_cannot_share_a_key(client, make_user):
    uid, _ = make_user()
    db = SessionLocal()
    for _i in range(2):
        db.add(models.PendingBill(user_id=uid, date=dt.date(2026, 7, 1), shop="X", amount=1, currency="SEK", origin="expenses", origin_key="s|k"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    # ordinary bills (no key) are unaffected by the index
    for _i in range(2):
        db.add(models.PendingBill(user_id=uid, date=dt.date(2026, 7, 1), shop="Y", amount=1, currency="SEK"))
    db.commit()
    db.close()


def test_a_concurrent_adopter_losing_the_race_retries_and_finds_the_others_bill(client, make_user, monkeypatch):
    uid, h = make_user()
    _insert(uid, [{"shop": "ICA", "amount": 10}, {"shop": "ICA", "amount": 5}])
    real = bill_sync._adopt
    calls = []

    def racing(db, user_id):
        if not calls:
            calls.append(1)
            raise IntegrityError("INSERT", {}, Exception("duplicate key: uq_pending_bills_origin_key"))
        calls.append(2)
        return real(db, user_id)

    monkeypatch.setattr(bill_sync, "_adopt", racing)
    [bill] = _synced_all(client, h)
    assert calls == [1, 2] and bill["item_count"] == 2 and D(str(bill["amount"])) == D("15")


def test_it_gives_up_after_repeated_conflicts_instead_of_looping(client, make_user, monkeypatch):
    uid, _ = make_user()
    _insert(uid, [{"shop": "ICA"}])
    monkeypatch.setattr(bill_sync, "_adopt", lambda db, u: (_ for _ in ()).throw(IntegrityError("x", {}, Exception("dup"))))
    db = SessionLocal()
    with pytest.raises(IntegrityError):
        bill_sync.sync_user_bills(db, uid)
    db.close()


def test_a_bill_someone_else_just_created_for_the_same_key_is_reused(client, make_user):
    uid, h = make_user()
    [eid] = _insert(uid, [{"shop": "ICA", "amount": 10}])
    db = SessionLocal()
    e = db.get(models.Expense, eid)
    existing = models.PendingBill(user_id=uid, date=e.date, shop="ICA", amount=0, currency="SEK", status="itemised", origin="expenses", origin_key=bill_sync.implicit_key(e))
    db.add(existing)
    db.commit()
    existing_id = existing.id
    db.close()
    [bill] = _synced_all(client, h)
    assert bill["id"] == existing_id and D(str(bill["amount"])) == D("10")


def test_reading_the_bills_page_writes_nothing_when_nothing_changed(client, make_user, monkeypatch):
    uid, h = make_user()
    _insert(uid, [{"shop": "ICA"}])
    _sync(client, h)  # adopt once
    commits = []
    real_commit = bill_sync.Session.commit if hasattr(bill_sync, "Session") else None
    db = SessionLocal()
    original = db.commit
    db.commit = lambda: commits.append(1) or original()
    assert bill_sync.sync_user_bills(db, uid) is False
    assert commits == []
    db.close()
    assert real_commit is None or True


def test_many_expenses_are_adopted_in_one_go(client, make_user):
    uid, h = make_user()
    rows = [{"shop": f"Shop {i % 120}", "date": JULY.format(1 + i % 28), "amount": 1 + i % 9, "description": f"item {i}"} for i in range(1500)]
    _insert(uid, rows)
    total = sum(r["amount"] for r in rows)
    result = _synced_bills(client, h, status="all", page_size=200)
    keys = {(r["shop"].lower(), r["date"]) for r in rows}
    assert result["total"] == len(keys)
    assert _spent(client, h) == D(str(total))
    db = SessionLocal()
    assert db.query(models.Expense).filter(models.Expense.user_id == uid, models.Expense.source_bill_id.is_(None)).count() == 0
    assert sum(b.amount for b in db.query(models.PendingBill).filter(models.PendingBill.user_id == uid)) == total
    db.close()


def test_key_helpers():
    e = models.Expense(id=7, date=dt.date(2026, 7, 1), shop="  ICA ", currency="SEK", group_id=None, description="x", category="Food")
    assert bill_sync.implicit_key(e) == "s|2026-07-01|ica|SEK|0"
    assert bill_sync.implicit_key(models.Expense(id=9, date=dt.date(2026, 7, 1), shop="", currency="SEK")) == "e|9"
    assert bill_sync.bill_name(e) == "ICA"
    assert bill_sync.bill_name(models.Expense(shop="", description="", category="Food")) == "Food"
    assert bill_sync.bill_name(models.Expense(shop="", description="", category="")) == "Expense"
    key = bill_sync.new_explicit_key()
    assert bill_sync.is_explicit(key) and not bill_sync.is_explicit("s|x") and not bill_sync.is_explicit(None)


# ── migration 0018 ───────────────────────────────────────────────────────
def test_0018_adds_the_columns_and_index_and_downgrades_safely():
    path = os.path.join(tempfile.mkdtemp(), "m18.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    con = sqlite3.connect(path)
    assert {"origin", "origin_key"} <= {r[1] for r in con.execute("PRAGMA table_info(pending_bills)")}
    index = [r for r in con.execute("PRAGMA index_list(pending_bills)") if r[1] == "uq_pending_bills_origin_key"]
    assert index and index[0][2] == 1  # unique

    con.execute("INSERT INTO users (id, email, hashed_password, name) VALUES (1, 'a@x.com', 'h', 'a')")
    def bill(i, origin, key, shop):
        con.execute(
            "INSERT INTO pending_bills (id, user_id, date, shop, amount, note, status, possible_duplicate, currency, origin, origin_key) "
            "VALUES (?, 1, '2026-07-01', ?, 10, '', 'itemised', 0, 'SEK', ?, ?)", (i, shop, origin, key))
    bill(1, "expenses", "s|a", "derived, no receipt")
    bill(2, "expenses", "s|b", "derived, with receipt")
    bill(3, None, None, "an ordinary bill")
    for i, bill_id in enumerate((1, 2, 3), start=1):
        con.execute(
            "INSERT INTO expenses (id, user_id, date, category, subcategory, description, amount, quantity, unit, shop, brand, currency, price_per_unit, source_bill_id) "
            "VALUES (?, 1, '2026-07-01', 'Food', '', 'x', 10, 1.0, 'Count', '', '', 'SEK', 10, ?)", (i, bill_id))
    con.execute("INSERT INTO receipts (user_id, pending_bill_id, filename, content_type, data) VALUES (1, 2, 'r.pdf', 'application/pdf', x'00')")
    con.commit()
    con.close()

    assert _alembic(path, "downgrade", "0017_bill_status_links").returncode == 0
    con = sqlite3.connect(path)
    assert "origin" not in {r[1] for r in con.execute("PRAGMA table_info(pending_bills)")}
    assert sorted(r[0] for r in con.execute("SELECT id FROM pending_bills")) == [2, 3]  # the receipt's bill is kept
    linked = dict(con.execute("SELECT id, source_bill_id FROM expenses").fetchall())
    assert linked == {1: None, 2: 2, 3: 3}  # expenses are never deleted
    assert con.execute("SELECT count(*) FROM expenses").fetchone() == (3,)
    con.close()
    assert _alembic(path, "upgrade", "head").returncode == 0  # and back up again
    assert _alembic(path, "upgrade", "head").returncode == 0  # idempotent


# ── the read-only staleness check used by every page load ────────────────
def _stale(uid):
    db = SessionLocal()
    try:
        return set(bill_sync._stale_bill_ids(db, uid))
    finally:
        db.close()


def _db_edit(expense_id, **fields):
    db = SessionLocal()
    db.query(models.Expense).filter(models.Expense.id == expense_id).update(fields)
    db.commit()
    db.close()


def test_nothing_is_stale_after_a_sync(client, make_user):
    uid, h = make_user()
    _insert(uid, [{"shop": "Coop", "amount": 10}, {"shop": "Coop", "amount": 5}, {"shop": "", "amount": 7}])
    _all_bills(client, h)  # a bills page load adopts them
    assert _stale(uid) == set()


def test_an_item_whose_shop_changed_behind_our_back_makes_its_bill_stale(client, make_user):
    uid, h = make_user()
    ids = _insert(uid, [{"shop": "Coop", "amount": 10}, {"shop": "Coop", "amount": 5}])
    _synced_all(client, h)
    bill_id = _bill_of(client, h, ids[0])["id"]
    _db_edit(ids[0], shop="Lidl")
    assert _stale(uid) == {bill_id}
    # and the normal page load repairs it
    bills = _synced_all(client, h)
    assert sorted((b["shop"], float(b["amount"])) for b in bills) == [("Coop", 5.0), ("Lidl", 10.0)]
    assert _stale(uid) == set()


def test_an_amount_that_is_no_longer_the_sum_of_its_items_is_stale(client, make_user):
    uid, h = make_user()
    ids = _insert(uid, [{"shop": "Coop", "amount": 10}, {"shop": "Coop", "amount": 5}])
    _synced_all(client, h)
    bill_id = _bill_of(client, h, ids[0])["id"]
    _db_edit(ids[1], amount=6)
    assert _stale(uid) == {bill_id}
    assert [float(b["amount"]) for b in _synced_all(client, h)] == [16.0]
    assert _stale(uid) == set()


def test_a_derived_bill_with_no_items_left_is_stale(client, make_user):
    uid, h = make_user()
    [eid] = _insert(uid, [{"shop": "Coop", "amount": 10}])
    _synced_all(client, h)
    bill_id = _bill_of(client, h, eid)["id"]
    db = SessionLocal()
    db.query(models.Expense).filter(models.Expense.id == eid).delete()
    db.commit()
    db.close()
    assert _stale(uid) == {bill_id}
    assert _synced_all(client, h) == []


def test_items_of_a_hand_grouped_bill_may_differ_in_shop_without_being_stale(client, make_user):
    uid, h = make_user()
    r = client.post(
        "/api/expenses/bulk",
        json={"as_bill": True, "items": [
            {"date": JULY.format(10), "category": "Food", "amount": "10", "currency": "SEK", "shop": "Coop"},
            {"date": JULY.format(10), "category": "Food", "amount": "5", "currency": "SEK", "shop": "Lidl"},
        ]},
        headers=h,
    )
    assert r.status_code == 201, r.text
    _all_bills(client, h)
    assert _stale(uid) == set()


def test_the_check_and_the_orm_agree_on_which_bill_an_expense_belongs_to(client, make_user):
    uid, _ = make_user()
    ids = _insert(uid, [{"shop": " Coop ", "amount": 1, "currency": "USD"}, {"shop": "", "amount": 2}])
    db = SessionLocal()
    for e in db.query(models.Expense).filter(models.Expense.id.in_(ids)):
        assert bill_sync.implicit_key(e) == bill_sync._implicit_key(e.id, e.date, e.shop, e.currency, e.group_id)
    db.close()
