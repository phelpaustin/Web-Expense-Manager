"""A bill recorded as a single total is a shop trip: it carries its shop, and is never an item price."""
import datetime as dt
from decimal import Decimal as D

import pytest
import sqlalchemy as sa

from app.db import models
from app.db.bill_shop_cleanup import fill_bill_total_shops
from app.db.database import SessionLocal
from app.logic import price_tracker as pt


def day(n):
    return (dt.date.today() - dt.timedelta(days=n)).isoformat()


def stored(client, h, **params):
    return client.get("/api/expenses", params={"page_size": 100, **params}, headers=h).json()["items"]


def new_bill(client, h, shop="ICA Maxi", amount="300", when=None):
    r = client.post("/api/pending-bills", json={"date": when or day(5), "shop": shop, "amount": amount}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def manual_mode(client, h):
    """Bills are not recorded as spending automatically; the user records each one."""
    assert client.post("/api/options/count-bills-as-spending", json={"enabled": False}, headers=h).status_code == 200


# --- every way a total gets recorded sets the shop -----------------------------------------

def test_a_bill_recorded_automatically_carries_its_shop(client, make_user):
    _, h = make_user()
    new_bill(client, h, "ICA Maxi", "300")

    [e] = stored(client, h)

    assert (e["shop"], e["description"], e["bill_total_only"]) == ("ICA Maxi", "ICA Maxi", True)


def test_recording_a_total_by_hand_carries_the_shop(client, make_user):
    _, h = make_user()
    manual_mode(client, h)
    bill = new_bill(client, h, "Lidl", "150")
    assert stored(client, h) == []

    assert client.post(f"/api/bills/{bill['id']}/record-total", json={"category": "Groceries"}, headers=h).status_code == 200

    [e] = stored(client, h)
    assert (e["shop"], e["description"], e["category"]) == ("Lidl", "Lidl", "Groceries")


def test_recording_several_totals_at_once_carries_each_shop(client, make_user):
    _, h = make_user()
    manual_mode(client, h)
    ids = [new_bill(client, h, shop, "100")["id"] for shop in ("Lidl", "Coop")]

    r = client.post("/api/bills/record-total", json={"ids": ids, "category": "Groceries"}, headers=h)

    assert r.status_code == 200, r.text
    assert sorted(e["shop"] for e in stored(client, h)) == ["Coop", "Lidl"]


def test_a_statement_upload_records_each_row_under_its_merchant(client, make_user):
    _, h = make_user()
    csv = f"Date,Shop,Amount\n{day(6)},ICA MAXI MALMO,300\n{day(4)},WILLYS,120\n".encode()

    r = client.post("/api/pending-bills/bulk-upload", files={"file": ("statement.csv", csv, "text/csv")}, headers=h)

    assert r.status_code == 201, r.text
    assert sorted(e["shop"] for e in stored(client, h)) == ["ICA MAXI MALMO", "WILLYS"]


def test_turning_an_itemised_bill_back_into_a_total_carries_the_shop(client, make_user):
    _, h = make_user()
    manual_mode(client, h)
    bill = new_bill(client, h, "Coop", "80")
    items = [{"date": bill["date"], "category": "Food", "description": "Rice", "amount": "80", "currency": "SEK", "shop": "Coop"}]
    r = client.post("/api/expenses/bulk", json={"items": items, "bill_id": bill["id"]}, headers=h)
    assert r.status_code in (200, 201), r.text
    assert [e["bill_total_only"] for e in stored(client, h)] == [False]

    r = client.post(f"/api/bills/{bill['id']}/revert-to-total", json={"category": "Groceries"}, headers=h)

    assert r.status_code == 200, r.text
    [e] = stored(client, h)
    assert (e["bill_total_only"], e["shop"], e["description"]) == (True, "Coop", "Coop")


def test_the_shop_filter_and_search_now_find_a_bill_total(client, make_user):
    _, h = make_user()
    new_bill(client, h, "ICA Maxi", "300")

    assert [e["shop"] for e in stored(client, h, shop="ica maxi")] == ["ICA Maxi"]
    assert len(stored(client, h, search="maxi")) == 1


def test_a_shops_spend_on_the_scorecard_includes_its_bill_totals(client, make_user):
    _, h = make_user()
    new_bill(client, h, "ICA Maxi", "300", when=day(4))
    new_bill(client, h, "ICA Maxi", "100", when=day(9))

    card = client.get("/api/analytics/shops", headers=h).json()

    assert card["unknown"]["purchases"] == 0
    assert [(s["shop"], float(s["spend"]), s["visits"]) for s in card["shops"]] == [("ICA Maxi", 400.0, 2)]


# --- a bill's total is not an item ---------------------------------------------------------

def test_recorded_bill_totals_never_appear_as_items_in_the_price_tracker(client, make_user):
    _, h = make_user()
    for n, amount in ((20, "300"), (10, "340"), (2, "420")):
        new_bill(client, h, "ICA Maxi", amount, when=day(n))

    assert client.get("/api/analytics/price-trends", headers=h).json() == []
    detail = client.get("/api/analytics/price-trends/detail", params={"item": "ICA Maxi"}, headers=h).json()
    assert detail["summary"] is None and detail["history"] == [] and detail["shops"] == []
    assert client.get("/api/analytics/price-trends/history", params={"item": "ICA Maxi"}, headers=h).json() == []
    assert client.get("/api/analytics/price-trends/shops", params={"item": "ICA Maxi"}, headers=h).json() == []


def test_a_real_item_that_shares_a_shops_name_is_still_tracked_without_the_totals(client, make_user):
    _, h = make_user()
    new_bill(client, h, "Cake", "300", when=day(20))   # a bill from a shop called "Cake"
    for n, price in ((12, 40), (3, 44)):
        r = client.post("/api/expenses", json={"date": day(n), "category": "Food", "description": "Cake", "amount": str(price),
                                               "quantity": 1, "unit": "Count", "shop": "Bakery", "currency": "SEK"}, headers=h)
        assert r.status_code == 201, r.text

    [row] = client.get("/api/analytics/price-trends", headers=h).json()

    assert (row["item"], row["purchases"], float(row["first_price"]), float(row["last_price"])) == ("Cake", 2, 40.0, 44.0)


def test_alias_suggestions_ignore_bill_totals_for_items_but_offer_the_shops(client, make_user):
    _, h = make_user()
    for shop in ("Willys", "Willys", "Wilys"):
        new_bill(client, h, shop, "100", when=day(5))

    items = client.get("/api/aliases/suggestions", params={"kind": "item"}, headers=h).json()["groups"]
    shops = client.get("/api/aliases/suggestions", params={"kind": "shop"}, headers=h).json()["groups"]

    assert items == []
    assert len(shops) == 1 and shops[0]["suggested"] == "Willys"


# --- the pure price-tracker functions agree ------------------------------------------------

def row(day_, price, item="Rice", shop="ICA", **extra):
    return {"description": item, "unit": "Count", "category": "Food", "date": dt.date(2026, 1, day_), "amount": D(price),
            "price_per_unit": D(price), "shop": shop, "brand": "", "bill_total_only": False, **extra}


def test_price_functions_skip_bill_totals_and_keep_real_purchases():
    rows = [row(1, 10), row(2, 12), row(3, 500, item="Rice", shop="Rice", bill_total_only=True), row(4, 900, item="ICA", bill_total_only=True)]

    [trend] = pt.price_trends(rows)

    assert (trend["item"], trend["purchases"]) == ("Rice", 2)
    detail = pt.price_detail(rows, "Rice")
    assert detail["summary"]["purchases"] == 2
    assert {s["shop"] for s in detail["shops"]} == {"ICA"}            # the totals' "Rice" shop is not here
    assert [p["price"] for p in pt.price_history(rows, "Rice")] == [10.0, 12.0]
    assert pt.price_trends([row(1, 900, item="ICA", bill_total_only=True), row(2, 800, item="ICA", bill_total_only=True)]) == []


def test_rows_without_the_flag_are_treated_as_items():
    plain = [{k: v for k, v in row(d, p).items() if k != "bill_total_only"} for d, p in ((1, 10), (2, 12))]

    assert pt.price_trends(plain)[0]["purchases"] == 2


# --- repairing old rows --------------------------------------------------------------------

def _legacy_expense(db, user_id, description, shop="", total_only=True, bill_id=None):
    db.execute(sa.insert(models.Expense.__table__).values(
        user_id=user_id, date=dt.date.today(), category="Food", subcategory="", description=description, amount=1,
        quantity=1, unit="Count", shop=shop, brand="", currency="SEK", price_per_unit=1, bill_total_only=total_only,
        source_bill_id=bill_id,
    ))


def _bill(db, user_id, shop):
    b = models.PendingBill(user_id=user_id, date=dt.date.today(), shop=shop, amount=1, currency="SEK", status="recorded")
    db.add(b)
    db.flush()
    return b.id


def _shops(db, user_id):
    rows = db.execute(sa.select(models.Expense.description, models.Expense.shop).where(models.Expense.user_id == user_id)).all()
    return {(d, s) for d, s in rows}


def test_the_repair_fills_old_totals_from_the_bill_or_else_the_description(make_user):
    uid, _ = make_user()
    other, _ = make_user()
    db = SessionLocal()
    try:
        linked = _bill(db, uid, "ICA Maxi")
        _legacy_expense(db, uid, "ICA", bill_id=linked)            # the bill is the source of truth
        _legacy_expense(db, uid, "Lidl")                            # its bill was deleted: description was the shop
        _legacy_expense(db, other, "Coop")                          # every user is repaired
        db.commit()

        changed = fill_bill_total_shops(db.connection())
        db.commit()

        assert changed >= 3
        assert _shops(db, uid) == {("ICA", "ICA Maxi"), ("Lidl", "Lidl")}
        assert _shops(db, other) == {("Coop", "Coop")}
    finally:
        db.close()


def test_the_repair_leaves_everything_else_alone_and_is_safe_to_repeat(make_user):
    uid, _ = make_user()
    db = SessionLocal()
    try:
        _legacy_expense(db, uid, "Rice", shop="", total_only=False)          # an ordinary expense with no shop
        _legacy_expense(db, uid, "ICA", shop="Hand-edited shop")             # already has a shop
        _legacy_expense(db, uid, "   ", shop="")                              # nothing to fill in from
        db.commit()

        fill_bill_total_shops(db.connection())
        db.commit()
        again = fill_bill_total_shops(db.connection())

        assert _shops(db, uid) == {("Rice", ""), ("ICA", "Hand-edited shop"), ("   ", "")}
        assert again == 0
    finally:
        db.close()
