"""A recorded total that is really one purchase can be marked as a single expense."""
from decimal import Decimal as D

from tests.test_bills_workflow import _bill, _bills, _expenses, _spent


def test_marking_a_total_as_single_makes_it_an_ordinary_expense(client, make_user):
    _, h = make_user()
    b = _bill(client, h, shop="Airbnb", amount="4125")
    assert b["status"] == "total_only"
    r = client.post(f"/api/bills/{b['id']}/mark-single", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "itemised"
    [e] = _expenses(client, h)
    assert e["bill_total_only"] is False and e["source_bill_id"] == b["id"]
    assert _spent(client, h) == D("4125")  # nothing counted twice
    assert _bills(client, h, status="itemised")["items"][0]["item_count"] == 1


def test_the_bill_then_follows_its_expense(client, make_user):
    _, h = make_user()
    b = _bill(client, h, shop="Airbnb", amount="100")
    client.post(f"/api/bills/{b['id']}/mark-single", headers=h)
    [e] = _expenses(client, h)
    assert client.put(f"/api/expenses/{e['id']}", json={"amount": "120"}, headers=h).status_code == 200
    [bill] = _bills(client, h, status="all")["items"]
    assert D(str(bill["amount"])) == D("120")
    assert client.delete(f"/api/expenses/{e['id']}", headers=h).status_code in (200, 204)
    assert _bills(client, h, status="all")["items"] == []  # a bill made from an expense goes with it


def test_only_a_total_only_bill_can_be_marked(client, make_user):
    _, h = make_user()
    b = _bill(client, h)
    client.post(f"/api/bills/{b['id']}/mark-single", headers=h)
    assert client.post(f"/api/bills/{b['id']}/mark-single", headers=h).status_code == 409
    assert client.post("/api/bills/99999/mark-single", headers=h).status_code == 404


def test_another_users_bill_is_not_reachable(client, make_user):
    _, h1 = make_user()
    _, h2 = make_user()
    b = _bill(client, h1)
    assert client.post(f"/api/bills/{b['id']}/mark-single", headers=h2).status_code == 404
