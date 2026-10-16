"""Bills workflow: to itemise -> total only -> itemised, counted as spending from the start."""
import datetime as dt
import os
import sqlite3
import tempfile
from decimal import Decimal

import pytest

from app.db import models
from app.db.database import SessionLocal
from tests.test_migration_0015 import _alembic

TODAY = dt.date.today().isoformat()
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
D = Decimal


def _setting(client, h, enabled):
    r = client.post("/api/options/count-bills-as-spending", json={"enabled": enabled}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _bill(client, h, shop="Lidl", amount="35.91", date=TODAY, **kw):
    r = client.post("/api/pending-bills", json={"date": date, "shop": shop, "amount": amount, **kw}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _bills(client, h, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/api/bills?{q}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _expenses(client, h, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(f"/api/expenses?{q}&page_size=200", headers=h).json()["items"]


def _spent(client, h):
    return D(str(client.get("/api/expenses/summary", headers=h).json()["total"]))


def _statement(rows):
    return ("Date,Description,Amount\n" + "\n".join(f"{d},{s},{a}" for d, s, a in rows) + "\n").encode()


def _import(client, h, rows):
    r = client.post("/api/pending-bills/bulk-upload", files={"file": ("s.csv", _statement(rows), "text/csv")}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


# ── the setting ──────────────────────────────────────────────────────────
def test_setting_defaults_on_and_can_be_toggled(client, make_user):
    _, h = make_user()
    assert client.get("/api/options", headers=h).json()["count_bills_as_spending"] is True
    assert _setting(client, h, False)["count_bills_as_spending"] is False
    assert client.get("/api/options", headers=h).json()["count_bills_as_spending"] is False
    assert _setting(client, h, True)["count_bills_as_spending"] is True


# ── counted as spending straight away (setting on) ───────────────────────
def test_new_bill_is_recorded_as_a_total_only_expense(client, make_user):
    _, h = make_user()
    b = _bill(client, h)
    assert b["status"] == "total_only" and b["item_count"] == 1
    [e] = _expenses(client, h)
    assert (e["category"], e["description"], D(str(e["amount"])), e["currency"]) == ("Bills", "Lidl", D("35.91"), "SEK")
    assert e["bill_total_only"] is True and e["source_bill_id"] == b["id"]
    assert _spent(client, h) == D("35.91")  # pooled into the totals budgets use
    assert "Bills" in client.get("/api/options", headers=h).json()["categories"]


def test_with_the_setting_off_a_bill_waits_and_counts_nothing(client, make_user):
    _, h = make_user()
    _setting(client, h, False)
    b = _bill(client, h)
    assert b["status"] == "pending" and b["item_count"] == 0
    assert _expenses(client, h) == [] and _spent(client, h) == 0


def test_total_only_expenses_count_against_budgets(client, make_user):
    _, h = make_user()
    client.put("/api/budgets", json={"category": "Bills", "amount": "100"}, headers=h)
    _bill(client, h, amount="60")
    status = client.get("/api/budgets/status", headers=h).json()
    bills_row = next(r for r in status if r["category"] == "Bills")
    assert D(str(bills_row["spent"])) == D("60")


# ── bank statement import ────────────────────────────────────────────────
def test_statement_import_records_totals_but_not_possible_duplicates(client, make_user):
    _, h = make_user()
    client.post("/api/expenses", json={"date": "2026-09-02", "category": "Food", "amount": "120.50", "currency": "SEK"}, headers=h)
    out = _import(client, h, [("2026-09-01", "ICA", "-80"), ("2026-09-02", "Coop", "-120.50"), ("2026-09-03", "Willys", "-45.30")])
    assert out["created"] == 3 and out["possible_duplicates"] == 1 and out["auto_recorded"] == 2
    counts = _bills(client, h)["counts"]
    # the expense typed in earlier is also a bill now (made from expenses, itemised)
    assert counts == {"pending": 1, "total_only": 2, "itemised": 1, "all": 4}
    [typed] = _bills(client, h, status="itemised")["items"]
    assert typed["from_expenses"] is True and typed["item_count"] == 1
    [dup] = _bills(client, h, status="pending")["items"]
    assert dup["shop"] == "Coop" and dup["possible_duplicate"] is True
    assert _spent(client, h) == D("120.50") + D("80") + D("45.30")  # the pre-existing expense + 2 recorded; no double count


def test_statement_import_with_the_setting_off_records_nothing(client, make_user):
    _, h = make_user()
    _setting(client, h, False)
    out = _import(client, h, [("2026-09-01", "ICA", "-80"), ("2026-09-03", "Willys", "-45.30")])
    assert out["created"] == 2 and out["auto_recorded"] == 0
    assert _bills(client, h)["counts"]["pending"] == 2 and _spent(client, h) == 0


# ── record total / undo ──────────────────────────────────────────────────
def test_record_total_links_the_expense_and_learns_the_category(client, make_user):
    _, h = make_user()
    _setting(client, h, False)
    b = _bill(client, h, shop="ICA Maxi", amount="199.5")
    out = client.post(f"/api/bills/{b['id']}/record-total", json={"category": "Groceries"}, headers=h).json()
    assert out["status"] == "total_only" and out["item_count"] == 1
    [e] = _expenses(client, h)
    assert e["category"] == "Groceries" and e["bill_total_only"] and e["source_bill_id"] == b["id"]
    assert "Groceries" in client.get("/api/options", headers=h).json()["categories"]


def test_bulk_record_total_skips_what_it_should(client, make_user):
    _, h = make_user()
    _setting(client, h, False)
    ok1, ok2 = _bill(client, h, shop="A", amount="10"), _bill(client, h, shop="B", amount="20")
    done = _bill(client, h, shop="Done", amount="5")
    client.post(f"/api/bills/{done['id']}/record-total", headers=h)
    client.post("/api/expenses", json={"date": "2026-09-02", "category": "Food", "amount": "7", "currency": "SEK"}, headers=h)
    dup = _import(client, h, [("2026-09-02", "Dup", "-7")])
    [dup_bill] = [b for b in _bills(client, h)["items"] if b["shop"] == "Dup"]
    out = client.post(
        "/api/bills/record-total",
        json={"ids": [ok1["id"], ok2["id"], done["id"], dup_bill["id"], 999999], "category": "Bills"},
        headers=h,
    ).json()
    assert out["recorded"] == 2
    reasons = {s["id"]: s["reason"] for s in out["skipped"]}
    assert "Already" in reasons[done["id"]] and "duplicate" in reasons[dup_bill["id"]].lower() and "not found" in reasons[999999].lower()
    assert _bills(client, h)["counts"]["pending"] == 1  # only the flagged duplicate is left to review
    # once the user says it is not a duplicate it can be recorded
    assert client.post(f"/api/pending-bills/{dup_bill['id']}/dismiss-duplicate", headers=h).json()["possible_duplicate"] is False
    assert client.post("/api/bills/record-total", json={"ids": [dup_bill["id"]]}, headers=h).json()["recorded"] == 1


def test_undo_removes_the_total_and_returns_the_bill_to_pending(client, make_user):
    _, h = make_user()
    b = _bill(client, h)  # auto-recorded
    assert _spent(client, h) == D("35.91")
    out = client.post(f"/api/bills/{b['id']}/undo", headers=h)
    assert out.status_code == 200 and out.json()["status"] == "pending" and out.json()["item_count"] == 0
    assert _expenses(client, h) == [] and _spent(client, h) == 0
    assert client.post(f"/api/bills/{b['id']}/undo", headers=h).status_code == 409  # nothing left to undo


def test_deleting_the_total_only_expense_reopens_the_bill(client, make_user):
    _, h = make_user()
    b = _bill(client, h)
    [e] = _expenses(client, h)
    assert client.delete(f"/api/expenses/{e['id']}", headers=h).status_code == 204
    assert _bills(client, h, status="all")["items"][0]["status"] == "pending"  # not a bill claiming spend that is gone
    assert client.post(f"/api/bills/{b['id']}/record-total", headers=h).status_code == 200  # and it can be recorded again


# ── itemise later ────────────────────────────────────────────────────────
def _items(*amounts, shop="Lidl"):
    return [{"date": TODAY, "category": "Food", "description": f"item {i}", "amount": str(a), "shop": shop} for i, a in enumerate(amounts)]


def test_itemising_a_total_only_bill_replaces_the_single_line(client, make_user):
    _, h = make_user()
    b = _bill(client, h, amount="100")
    assert _spent(client, h) == D("100")
    r = client.post("/api/expenses/bulk", json={"items": _items(60, 30, 10), "bill_id": b["id"]}, headers=h)
    assert r.status_code == 201, r.text
    assert all(e["source_bill_id"] == b["id"] and e["bill_total_only"] is False for e in r.json())
    rows = _expenses(client, h)
    assert len(rows) == 3 and not any(e["bill_total_only"] for e in rows)  # the placeholder is gone
    assert _spent(client, h) == D("100")  # replaced, not added on top
    bill = _bills(client, h, status="all")["items"][0]
    assert bill["status"] == "itemised" and bill["item_count"] == 3


def test_itemising_a_pending_bill_directly(client, make_user):
    _, h = make_user()
    _setting(client, h, False)
    b = _bill(client, h, amount="50")
    assert client.post("/api/expenses/bulk", json={"items": _items(30, 20), "bill_id": b["id"]}, headers=h).status_code == 201
    assert _bills(client, h, status="itemised")["total"] == 1 and _spent(client, h) == D("50")


def test_items_that_differ_from_the_bill_total_are_allowed(client, make_user):
    """The app warns about a mismatch in the UI; the server doesn't block a discount or rounding."""
    _, h = make_user()
    b = _bill(client, h, amount="100")
    assert client.post("/api/expenses/bulk", json={"items": _items(90), "bill_id": b["id"]}, headers=h).status_code == 201
    assert _spent(client, h) == D("90")


def test_a_bill_can_only_be_itemised_once(client, make_user):
    _, h = make_user()
    b = _bill(client, h, amount="100")
    assert client.post("/api/expenses/bulk", json={"items": _items(100), "bill_id": b["id"]}, headers=h).status_code == 201
    again = client.post("/api/expenses/bulk", json={"items": _items(100), "bill_id": b["id"]}, headers=h)
    assert again.status_code == 409
    assert len(_expenses(client, h)) == 1  # no duplicate items


def test_bulk_without_bill_id_is_unchanged(client, make_user):
    _, h = make_user()
    r = client.post("/api/expenses/bulk", json={"items": _items(5, 6)}, headers=h)
    assert r.status_code == 201 and all(e["source_bill_id"] is None for e in r.json())


def test_receipt_stays_attached_through_itemising(client, make_user):
    _, h = make_user()
    b = _bill(client, h, amount="100")
    assert client.post(f"/api/pending-bills/{b['id']}/receipt", files={"file": ("r.pdf", PDF, "application/pdf")}, headers=h).status_code == 200
    client.post("/api/expenses/bulk", json={"items": _items(100), "bill_id": b["id"]}, headers=h)
    bill = _bills(client, h, status="itemised")["items"][0]
    assert bill["has_receipt"] is True
    assert client.get(f"/api/pending-bills/{b['id']}/receipt", headers=h).status_code == 200


def test_deleting_an_item_keeps_the_bill_itemised(client, make_user):
    _, h = make_user()
    b = _bill(client, h, amount="100")
    client.post("/api/expenses/bulk", json={"items": _items(60, 40), "bill_id": b["id"]}, headers=h)
    first = _expenses(client, h)[0]
    client.delete(f"/api/expenses/{first['id']}", headers=h)
    assert _bills(client, h, status="all")["items"][0]["status"] == "itemised"


# ── deleting bills ───────────────────────────────────────────────────────
def test_delete_rules(client, make_user):
    _, h = make_user()
    _setting(client, h, False)
    pending = _bill(client, h, shop="P")
    assert client.delete(f"/api/pending-bills/{pending['id']}", headers=h).status_code == 204

    recorded = _bill(client, h, shop="R")
    client.post(f"/api/bills/{recorded['id']}/record-total", headers=h)
    blocked = client.delete(f"/api/pending-bills/{recorded['id']}", headers=h)
    assert blocked.status_code == 409 and "Undo" in blocked.json()["detail"]

    itemised = _bill(client, h, shop="I", amount="50")
    client.post("/api/expenses/bulk", json={"items": _items(50), "bill_id": itemised["id"]}, headers=h)
    assert client.delete(f"/api/pending-bills/{itemised['id']}", headers=h).status_code == 204
    kept = [e for e in _expenses(client, h) if e["description"] == "item 0"]
    # the expenses stay, and are filed under a bill made from expenses so they are still on the Bills page
    assert len(kept) == 1 and kept[0]["source_bill_id"] is not None
    rehomed = client.get(f"/api/bills/{kept[0]['source_bill_id']}", headers=h).json()
    assert rehomed["from_expenses"] is True and rehomed["status"] == "itemised"


def test_bulk_delete(client, make_user):
    _, h = make_user()
    _setting(client, h, False)
    a, b = _bill(client, h, shop="A"), _bill(client, h, shop="B")
    client.post(f"/api/bills/{b['id']}/record-total", headers=h)
    out = client.post("/api/bills/bulk-delete", json={"ids": [a["id"], b["id"]]}, headers=h).json()
    assert out["deleted"] == 1 and out["skipped"][0]["id"] == b["id"]


# ── the list ─────────────────────────────────────────────────────────────
def test_list_paginates_filters_sorts_and_counts(client, make_user):
    _, h = make_user()
    _setting(client, h, False)
    for i in range(7):
        _bill(client, h, shop=f"Shop {i}", amount=str(10 + i), date=f"2026-08-{10 + i:02d}")
    done = _bill(client, h, shop="Recorded", amount="5", date="2026-08-01")
    client.post(f"/api/bills/{done['id']}/record-total", headers=h)

    first = _bills(client, h, page_size=3, page=1)
    assert [b["shop"] for b in first["items"]] == ["Shop 6", "Shop 5", "Shop 4"]  # newest first
    assert first["total"] == 7 and first["page"] == 1 and first["page_size"] == 3
    assert first["counts"] == {"pending": 7, "total_only": 1, "itemised": 0, "all": 8}
    last = _bills(client, h, page_size=3, page=3)
    assert [b["shop"] for b in last["items"]] == ["Shop 0"]
    assert _bills(client, h, page_size=3, page=9)["items"] == []

    assert _bills(client, h, status="total_only")["items"][0]["shop"] == "Recorded"
    assert _bills(client, h, status="all")["total"] == 8
    assert [b["shop"] for b in _bills(client, h, sort="amount_desc", page_size=2)["items"]] == ["Shop 6", "Shop 5"]
    assert [b["shop"] for b in _bills(client, h, sort="amount_asc", page_size=1)["items"]] == ["Shop 0"]
    assert [b["shop"] for b in _bills(client, h, sort="shop", page_size=2)["items"]] == ["Shop 0", "Shop 1"]
    assert [b["shop"] for b in _bills(client, h, sort="date_asc", page_size=1)["items"]] == ["Shop 0"]

    found = _bills(client, h, q="shop%203")
    assert [b["shop"] for b in found["items"]] == ["Shop 3"]
    assert found["counts"]["all"] == 1  # tab counts follow the search
    ranged = _bills(client, h, date_from="2026-08-12", date_to="2026-08-14")
    assert [b["shop"] for b in ranged["items"]] == ["Shop 4", "Shop 3", "Shop 2"]


@pytest.mark.parametrize("params", ["status=bogus", "sort=bogus", "page=0", "page_size=0", "page_size=201"])
def test_list_rejects_bad_parameters(client, make_user, params):
    _, h = make_user()
    assert client.get(f"/api/bills?{params}", headers=h).status_code == 422


def test_expenses_list_filters_total_only_and_exposes_the_link(client, make_user):
    _, h = make_user()
    b = _bill(client, h, shop="Totals only")
    client.post("/api/expenses", json={"date": TODAY, "category": "Food", "amount": "3", "currency": "SEK"}, headers=h)
    only = _expenses(client, h, total_only="true")
    assert [e["source_bill_id"] for e in only] == [b["id"]]
    assert len(_expenses(client, h, total_only="false")) == 1
    assert len(_expenses(client, h)) == 2


# ── receipts: attach / create (nothing is read from the file) ───────────
def _upload(client, h, name="lidl.pdf", **data):
    return client.post("/api/pending-bills/upload", files={"file": (name, PDF, "application/pdf")}, data=data, headers=h)


def test_receipt_creates_an_empty_bill_to_itemise_and_counts_nothing(client, make_user):
    _, h = make_user()
    r = _upload(client, h, name="IMG_2031.pdf")
    assert r.status_code == 201 and r.json()["result"] == "created"
    bill = r.json()["bill"]
    assert bill["status"] == "pending" and bill["has_receipt"] is True
    assert bill["shop"] == "IMG_2031.pdf" and D(str(bill["amount"])) == 0 and bill["date"] == TODAY
    assert _spent(client, h) == 0


def test_receipt_never_matches_or_merges_with_an_existing_bill(client, make_user):
    _, h = make_user()
    _bill(client, h, shop="LIDL145MALMOBA", amount="35.91", date=TODAY)
    r = _upload(client, h)
    assert r.status_code == 201 and r.json()["result"] == "created"
    assert _bills(client, h, status="all")["total"] == 2
    assert _spent(client, h) == D("35.91")  # the empty receipt bill adds nothing


def test_receipt_uses_what_you_type_and_nothing_else(client, make_user):
    _, h = make_user()
    r = _upload(client, h, shop="Corner shop", amount="12.50")
    bill = r.json()["bill"]
    assert bill["shop"] == "Corner shop" and D(str(bill["amount"])) == D("12.50")
    assert bill["status"] == "total_only" and _spent(client, h) == D("12.50")  # "count bills as spending" is on


def test_receipt_can_be_attached_to_an_existing_bill(client, make_user):
    _, h = make_user()
    existing = _bill(client, h, shop="LIDL145MALMOBA", amount="35.91", date="2026-07-21")
    attached = _upload(client, h, attach_to=str(existing["id"]))
    assert attached.status_code == 200 and attached.json()["result"] == "attached"
    assert attached.json()["bill"]["has_receipt"] is True and _spent(client, h) == D("35.91")
    assert _bills(client, h, status="all")["total"] == 1


def test_itemising_an_empty_receipt_bill_fills_in_what_you_typed(client, make_user):
    _, h = make_user()
    bill = _upload(client, h, name="IMG_9.pdf").json()["bill"]
    items = [
        {"date": "2026-07-22", "category": "Food", "description": "Milk", "shop": "Lidl", "amount": "20", "currency": "SEK"},
        {"date": "2026-07-22", "category": "Food", "description": "Bread", "shop": "Lidl", "amount": "30", "currency": "SEK"},
    ]
    r = client.post("/api/expenses/bulk", json={"items": items, "bill_id": bill["id"]}, headers=h)
    assert r.status_code in (200, 201), r.text
    after = client.get(f"/api/bills/{bill['id']}", headers=h).json()
    assert after["status"] == "itemised" and D(str(after["amount"])) == D("50")
    assert after["shop"] == "Lidl" and after["date"] == "2026-07-22"
    assert _spent(client, h) == D("50")


def test_itemising_a_bill_with_a_known_total_keeps_its_details(client, make_user):
    _, h = make_user()
    bill = _bill(client, h, shop="LIDL145MALMOBA", amount="35.91", date="2026-07-21")
    items = [{"date": "2026-07-22", "category": "Food", "description": "Milk", "shop": "Lidl", "amount": "20", "currency": "SEK"}]
    client.post("/api/expenses/bulk", json={"items": items, "bill_id": bill["id"]}, headers=h)
    after = client.get(f"/api/bills/{bill['id']}", headers=h).json()
    assert after["shop"] == "LIDL145MALMOBA" and D(str(after["amount"])) == D("35.91")


def test_receipt_bill_can_have_its_total_recorded_by_hand(client, make_user):
    _, h = make_user()
    bill = _upload(client, h).json()["bill"]
    assert client.post(f"/api/bills/{bill['id']}/record-total", json={"amount": "8"}, headers=h).status_code == 200
    assert _spent(client, h) == D("8")


# ── other users' bills ───────────────────────────────────────────────────
def test_users_cannot_touch_each_others_bills(client, make_user):
    _, a = make_user()
    _, b = make_user()
    bill = _bill(client, a, shop="Private")
    assert _bills(client, b, status="all")["total"] == 0
    for call in (
        lambda: client.post(f"/api/bills/{bill['id']}/record-total", headers=b),
        lambda: client.post(f"/api/bills/{bill['id']}/undo", headers=b),
        lambda: client.delete(f"/api/pending-bills/{bill['id']}", headers=b),
        lambda: client.post("/api/expenses/bulk", json={"items": _items(5), "bill_id": bill["id"]}, headers=b),
        lambda: client.post(f"/api/pending-bills/{bill['id']}/dismiss-duplicate", headers=b),
    ):
        assert call().status_code == 404
    skipped = client.post("/api/bills/record-total", json={"ids": [bill["id"]]}, headers=b).json()
    assert skipped["recorded"] == 0 and "not found" in skipped["skipped"][0]["reason"].lower()
    assert client.post("/api/bills/bulk-delete", json={"ids": [bill["id"]]}, headers=b).json()["deleted"] == 0
    assert _bills(client, a, status="all")["total"] == 1


# ── migration 0017 ───────────────────────────────────────────────────────
def test_0017_links_old_total_only_expenses_and_copies_manual_bills():
    path = os.path.join(tempfile.mkdtemp(), "legacy17.db")
    assert _alembic(path, "upgrade", "head").returncode == 0
    assert _alembic(path, "downgrade", "0016_display_currency").returncode == 0  # back to the pre-0017 shape
    con = sqlite3.connect(path)
    cols = {r[1] for r in con.execute("PRAGMA table_info(expenses)")}
    assert "source_bill_id" not in cols and "bill_total_only" not in cols

    def expense(uid, date, desc, amount, category="Bills"):
        con.execute(
            "INSERT INTO expenses (user_id, date, category, subcategory, description, amount, quantity, unit, shop, brand, currency, price_per_unit) "
            "VALUES (?, ?, ?, '', ?, ?, 1.0, 'Count', '', '', 'SEK', ?)",
            (uid, date, category, desc, amount, amount),
        )

    def bill(uid, date, shop, amount, status):
        con.execute(
            "INSERT INTO pending_bills (user_id, date, shop, amount, note, status, possible_duplicate, currency) VALUES (?, ?, ?, ?, '', ?, 0, 'SEK')",
            (uid, date, shop, amount, status),
        )

    con.execute("INSERT INTO users (id, email, hashed_password, name) VALUES (1, 'a@x.com', 'h', 'a')")
    con.execute(
        "INSERT INTO user_options (user_id, categories, subcategories, units, shops, base_currency, budget_period, budget_rollover) "
        "VALUES (1, '[]', '{}', '[]', '[]', 'SEK', 'Monthly', 0)"
    )
    # 1) itemised bill with exactly one matching one-line expense -> linked, becomes total_only
    bill(1, "2026-07-21", "LIDL", 35.91, "itemised"); expense(1, "2026-07-21", "LIDL", 35.91)
    # 2) ambiguous: two identical matching expenses -> left alone
    bill(1, "2026-07-22", "ICA", 50, "itemised"); expense(1, "2026-07-22", "ICA", 50); expense(1, "2026-07-22", "ICA", 50)
    # 3) itemised bill with no matching expense (it was itemised with real items elsewhere) -> untouched
    bill(1, "2026-07-23", "COOP", 70, "itemised")
    # 4) an expense in another category is not a total-only placeholder
    bill(1, "2026-07-24", "WILLYS", 20, "itemised"); expense(1, "2026-07-24", "WILLYS", 20, category="Food")
    # 5) a pending bill is never touched
    bill(1, "2026-07-25", "PENDING", 5, "pending"); expense(1, "2026-07-25", "PENDING", 5)
    # manual ledger bills: one has an identical expense (-> flagged possible duplicate), one does not
    con.execute("INSERT INTO manual_bills (user_id, date, shop, amount, note, currency) VALUES (1, '2026-07-26', 'Rent', 9000, 'monthly', 'SEK')")
    con.execute("INSERT INTO manual_bills (user_id, date, shop, amount, note, currency) VALUES (1, '2026-07-21', 'Twin', 35.91, '', 'SEK')")
    con.commit()
    con.close()

    assert _alembic(path, "upgrade", "head").returncode == 0
    con = sqlite3.connect(path)
    status = dict(con.execute("SELECT shop, status FROM pending_bills WHERE note NOT IN ('monthly', 'Manual entry')").fetchall())
    assert status == {"LIDL": "total_only", "ICA": "itemised", "COOP": "itemised", "WILLYS": "itemised", "PENDING": "pending"}
    linked = con.execute("SELECT description, bill_total_only FROM expenses WHERE source_bill_id IS NOT NULL").fetchall()
    assert linked == [("LIDL", 1)]
    manual = {r[0]: r for r in con.execute("SELECT shop, status, possible_duplicate, note FROM pending_bills WHERE shop IN ('Rent', 'Twin')")}
    assert manual["Rent"][1:] == ("pending", 0, "monthly") and manual["Twin"][1] == "pending" and manual["Twin"][2] == 1 and manual["Twin"][3] == "Manual entry"
    assert con.execute("SELECT count_bills_as_spending FROM user_options").fetchone() == (1,)  # on for existing users
    assert con.execute("SELECT count(*) FROM manual_bills").fetchone() == (2,)  # the old table is left alone
    con.close()

    assert _alembic(path, "upgrade", "head").returncode == 0  # idempotent: nothing is linked or copied twice
    con = sqlite3.connect(path)
    assert con.execute("SELECT count(*) FROM pending_bills").fetchone() == (7,)
    con.close()
    assert _alembic(path, "downgrade", "0016_display_currency").returncode == 0
