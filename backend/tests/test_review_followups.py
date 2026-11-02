"""Smaller fixes from the full code review."""
import pytest

from app.api import groups as groups_api
from app.core.rate_limit import limiter


@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.reset()
    yield
    limiter.reset()


def test_a_category_with_a_slash_in_its_name_can_be_deleted(client, make_user):
    _, h = make_user()
    r = client.post("/api/options/category", json={"name": "Food/Drink"}, headers=h)
    assert r.status_code == 200 and "Food/Drink" in r.json()["categories"]
    r = client.delete("/api/options/category/Food%2FDrink", headers=h)
    assert r.status_code == 200
    assert "Food/Drink" not in r.json()["categories"]


def test_a_space_stops_taking_new_invitations_at_the_cap(client, make_user, monkeypatch):
    monkeypatch.setattr(groups_api, "MAX_PENDING_INVITES", 2)
    monkeypatch.setattr(groups_api, "send_email", lambda *a, **k: True)
    _, h = make_user()
    gid = client.post("/api/groups", json={"name": "G", "space_type": "household"}, headers=h).json()["id"]
    for n in range(2):
        assert client.post(f"/api/groups/{gid}/invite", json={"email": f"cap{n}@example.com", "role": "viewer"}, headers=h).status_code == 201
    over = client.post(f"/api/groups/{gid}/invite", json={"email": "cap9@example.com", "role": "viewer"}, headers=h)
    assert over.status_code == 400 and "pending invitations" in over.json()["detail"]
    # inviting someone who is already pending is still the same quiet answer
    assert client.post(f"/api/groups/{gid}/invite", json={"email": "cap0@example.com", "role": "viewer"}, headers=h).status_code == 201


def test_a_trip_with_an_unknown_status_is_refused(client, make_user):
    _, h = make_user()
    r = client.post("/api/trips", json={"name": "Rome", "status": "Nonsense"}, headers=h)
    assert r.status_code == 422
    assert client.post("/api/trips", json={"name": "Rome", "status": "Planned"}, headers=h).status_code == 201


def test_the_digest_endpoint_is_rate_limited(client):
    codes = [client.post("/api/alerts/send-digest", headers={"X-Cron-Secret": "wrong"}).status_code for _ in range(32)]
    assert codes[0] == 403
    assert codes[-1] == 429


def test_an_expense_of_a_deleted_account_cannot_be_moved_out_of_its_space(client, make_user):
    from app.db import models
    from app.db.database import SessionLocal

    _, oh = make_user()
    _, mh = make_user()
    gid = client.post("/api/groups", json={"name": "G", "space_type": "household"}, headers=oh).json()["id"]
    eid = client.post("/api/expenses", json={"date": "2026-01-05", "category": "Food", "amount": 10, "group_id": gid}, headers=oh).json()["id"]
    db = SessionLocal()
    try:
        db.get(models.Expense, eid).user_id = None
        db.commit()
    finally:
        db.close()
    r = client.put(f"/api/expenses/{eid}", json={"group_id": None}, headers=oh)
    assert r.status_code == 400 and "deleted account" in r.json()["detail"]
    r = client.post("/api/expenses/bulk-update", json={"ids": [eid], "changes": {"group_id": None}}, headers=oh)
    assert r.status_code == 400


def test_shop_list_ignores_case_when_adding(client, make_user):
    _, h = make_user()
    client.post("/api/options/shop", json={"name": "ICA Maxi"}, headers=h)
    shops = client.post("/api/options/shop", json={"name": "ica maxi"}, headers=h).json()["shops"]
    assert sum(1 for s in shops if s.lower() == "ica maxi") == 1


def test_filtering_by_uncategorized_also_finds_expenses_with_no_category(client, make_user):
    from app.db import models
    from app.db.database import SessionLocal

    uid, h = make_user()
    named = client.post("/api/expenses", json={"date": "2026-03-01", "category": "Uncategorized", "amount": 5}, headers=h).json()["id"]
    blank = client.post("/api/expenses", json={"date": "2026-03-02", "category": "Food", "amount": 6}, headers=h).json()["id"]
    client.post("/api/expenses", json={"date": "2026-03-03", "category": "Food", "amount": 7}, headers=h)
    db = SessionLocal()
    try:
        db.get(models.Expense, blank).category = ""
        db.commit()
    finally:
        db.close()
    ids = {e["id"] for e in client.get("/api/expenses?category=Uncategorized", headers=h).json()["items"]}
    assert ids == {named, blank}
    assert len(client.get("/api/expenses?category=Food", headers=h).json()["items"]) == 1
