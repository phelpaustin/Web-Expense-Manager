"""Amounts and quantities larger than the database columns can hold are refused, not a 500."""
from app.api.expenses import MAX_PRICE_PER_UNIT, _price_per_unit
from decimal import Decimal


def _csv(rows):
    return ("Date,Category,PricePaid,Quantity\n" + "\n".join(rows) + "\n").encode()


def test_file_import_skips_an_amount_too_large_for_the_column_and_keeps_the_rest(client, make_user):
    _, h = make_user()
    body = _csv(["2026-01-05,Food,12.50,1", "2026-01-06,Food,99999999999.00,1"])
    r = client.post("/api/expenses/import", files={"file": ("e.csv", body)}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 1
    assert any("too large" in str(s).lower() for s in r.json().get("skipped_rows", []) + r.json().get("errors", []))


def test_file_import_resets_a_silly_quantity_to_one(client, make_user):
    _, h = make_user()
    r = client.post("/api/expenses/import", files={"file": ("e.csv", _csv(["2026-01-05,Food,10,5000000000"]))}, headers=h)
    assert r.status_code == 200, r.text
    items = client.get("/api/expenses", headers=h).json()["items"]
    assert items[0]["quantity"] == 1


def test_api_refuses_a_quantity_above_the_limit(client, make_user):
    _, h = make_user()
    r = client.post(
        "/api/expenses",
        json={"date": "2026-01-05", "category": "Food", "amount": 10, "quantity": 5_000_000_000},
        headers=h,
    )
    assert r.status_code == 422


def test_price_per_unit_never_exceeds_its_column():
    assert _price_per_unit(Decimal("9999999999.99"), 0.001) == MAX_PRICE_PER_UNIT
    assert _price_per_unit(Decimal("10"), 4) == Decimal("2.5000")


def test_file_import_is_not_blocked_by_someone_elses_shared_expense(client, make_user):
    oid, oh = make_user()
    mid, mh = make_user()
    g = client.post("/api/groups", json={"name": "G", "space_type": "household"}, headers=oh).json()["id"]
    client.post(
        "/api/expenses",
        json={"date": "2026-01-05", "category": "Food", "description": "", "amount": 12.5, "group_id": g},
        headers=oh,
    )
    # the owner's own personal import of an identical row is new: the shared one is not a duplicate of it
    r = client.post("/api/expenses/import", files={"file": ("e.csv", _csv(["2026-01-05,Food,12.50,1"]))}, headers=oh)
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 1
