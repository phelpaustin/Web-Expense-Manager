"""A bill kept as one total (rent, an Airbnb stay, a phone bill) is an ordinary expense to edit:
category, space and every other detail can change, and its bill follows without being reopened."""
from tests.test_bill_sync import _all_bills
from tests.test_bill_total_shop import day, new_bill, stored


def _the_expense_and_bill(client, h):
    [e] = stored(client, h)
    [b] = _all_bills(client, h)
    return e, b


def test_editing_the_category_and_space_of_a_total_only_expense_keeps_it_a_total(client, make_user):
    _, h = make_user()
    new_bill(client, h, "AIRBNB * HMEYK", "4378.81", day(5))
    trip = client.post("/api/groups", json={"name": "Norway"}, headers=h).json()["id"]
    e, b = _the_expense_and_bill(client, h)
    assert e["bill_total_only"] is True and b["status"] == "total_only"

    r = client.put(f"/api/expenses/{e['id']}", json={"category": "Travel", "group_id": trip}, headers=h)
    assert r.status_code == 200, r.text

    e2, b2 = _the_expense_and_bill(client, h)
    assert (e2["category"], e2["group_id"]) == ("Travel", trip)
    assert e2["bill_total_only"] is True            # still the single total, not itemised
    assert b2["status"] == "total_only"             # the Bills page still shows it as a total
    assert b2["id"] == b["id"]                      # the same bill, no duplicate


def test_editing_every_detail_of_a_total_only_expense_leaves_one_bill_and_still_a_total(client, make_user):
    _, h = make_user()
    new_bill(client, h, "RENT CO", "9000", day(10))
    e, b = _the_expense_and_bill(client, h)

    r = client.put(
        f"/api/expenses/{e['id']}",
        json={"date": day(3), "shop": "Landlord AB", "description": "October rent", "amount": 9500, "category": "Housing"},
        headers=h,
    )
    assert r.status_code == 200, r.text

    e2, b2 = _the_expense_and_bill(client, h)          # exactly one expense and one bill: nothing stray
    assert (e2["shop"], e2["description"], e2["category"], float(e2["amount"])) == ("Landlord AB", "October rent", "Housing", 9500.0)
    assert e2["date"] == day(3)
    assert e2["bill_total_only"] is True and b2["status"] == "total_only"
    assert b2["id"] == b["id"]                          # still the same bill, not reopened or duplicated
